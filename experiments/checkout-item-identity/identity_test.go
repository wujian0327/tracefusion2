// Test-only independent truth. Business source and compilation optimizations stay unchanged.
package main

import (
	"context"
	"encoding/json"
	"flag"
	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/connectivity"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"io"
	"net"
	"os"
	"runtime"
	"sync"
	"testing"
	"time"
	"unsafe"
)

func TestMain(m *testing.M) {
	var gate [1]byte
	if _, err := io.ReadFull(os.Stdin, gate[:]); err != nil {
		panic(err)
	}
	if err := flag.Set("test.run", "^TestTraceFusionItemIdentity$"); err != nil {
		panic(err)
	}
	os.Exit(m.Run())
}

type identityPeer struct {
	pb.UnimplementedProductCatalogServiceServer
	pb.UnimplementedCurrencyServiceServer
	mu     sync.Mutex
	fail   string
	counts map[string]int
}

func (p *identityPeer) fails(kind string) bool {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.counts[kind]++
	return kind == p.fail && p.counts[kind] == 2
}
func (p *identityPeer) GetProduct(ctx context.Context, r *pb.GetProductRequest) (*pb.Product, error) {
	if p.fails("product") {
		return nil, status.Error(codes.Unavailable, "fixture error")
	}
	return &pb.Product{Id: r.Id, PriceUsd: &pb.Money{CurrencyCode: "USD", Units: 7}}, nil
}
func (p *identityPeer) Convert(ctx context.Context, r *pb.CurrencyConversionRequest) (*pb.Money, error) {
	if p.fails("currency") {
		return nil, status.Error(codes.Unavailable, "fixture error")
	}
	return &pb.Money{CurrencyCode: r.ToCode, Units: r.From.Units * 2}, nil
}

func TestTraceFusionItemIdentity(t *testing.T) {
	name := os.Getenv("TRACEFUSION_IDENTITY_CASE")
	n, fail := 0, ""
	switch name {
	case "empty":
	case "one":
		n = 1
	case "equal-eight":
		n = 8
	case "equal-thirty-two":
		n = 32
	case "aliased-input":
		n = 3
	case "product-error-second":
		n = 4
		fail = "product"
	case "currency-error-second":
		n = 4
		fail = "currency"
	default:
		t.Fatal("unknown case", name)
	}
	peer := &identityPeer{fail: fail, counts: map[string]int{}}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := grpc.NewServer()
	pb.RegisterProductCatalogServiceServer(server, peer)
	pb.RegisterCurrencyServiceServer(server, peer)
	go server.Serve(listener)
	defer server.Stop()
	// Independent truth at the test client's RPC boundary. These references also
	// keep objects alive; addresses are not treated as lifetime-independent IDs.
	type conversionTruth struct {
		Input  *pb.Money
		Reply  *pb.Money
		Failed bool
	}
	var conversionMu sync.Mutex
	conversions := []conversionTruth{}
	interceptor := func(ctx context.Context, method string, req, reply interface{}, cc *grpc.ClientConn, invoke grpc.UnaryInvoker, opts ...grpc.CallOption) error {
		err := invoke(ctx, method, req, reply, cc, opts...)
		if request, ok := req.(*pb.CurrencyConversionRequest); ok {
			conversionMu.Lock()
			conversions = append(conversions, conversionTruth{request.From, reply.(*pb.Money), err != nil})
			conversionMu.Unlock()
		}
		return err
	}
	conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithUnaryInterceptor(interceptor))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	// Establish the transport before the measured order call. Do not warm the
	// target function: observation still covers exactly one invocation/process.
	connectCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	conn.Connect()
	for {
		state := conn.GetState()
		if state == connectivity.Ready {
			break
		}
		if !conn.WaitForStateChange(connectCtx, state) {
			t.Fatal("RPC transport not ready", connectCtx.Err())
		}
	}
	service := &checkoutService{productCatalogSvcConn: conn, currencySvcConn: conn}
	inputs := make([]*pb.CartItem, n)
	for i := range inputs {
		inputs[i] = &pb.CartItem{ProductId: "same-product", Quantity: 2}
	}
	if name == "aliased-input" {
		inputs[2] = inputs[0]
	}
	started := time.Now()
	result, err := service.prepOrderItems(context.Background(), inputs, "EUR")
	callElapsed := time.Since(started).Nanoseconds()
	if (err != nil) != (fail != "") {
		t.Fatal("unexpected error", err)
	}
	if err != nil && result != nil {
		t.Fatal("partial output on error")
	}
	if err == nil && len(result) != n {
		t.Fatal("output count")
	}
	inputPointers := []uint64{}
	output := []map[string]interface{}{}
	conversionMu.Lock()
	defer conversionMu.Unlock()
	expectedConversions := n
	if fail == "product" {
		expectedConversions = 1
	}
	if fail == "currency" {
		expectedConversions = 2
	}
	if len(conversions) != expectedConversions {
		t.Fatal("unexpected conversion count")
	}
	conversionRows := []map[string]interface{}{}
	seenReplies := map[*pb.Money]bool{}
	for _, c := range conversions {
		var resultPointer uint64
		if !c.Failed {
			if seenReplies[c.Reply] {
				t.Fatal("successful RPC replies unexpectedly aliased")
			}
			seenReplies[c.Reply] = true
			resultPointer = uint64(uintptr(unsafe.Pointer(c.Reply)))
		}
		// The original convertCurrency wrapper returns nil on error; a failed
		// RPC's allocated reply is not a successful wrapper-return source.
		conversionRows = append(conversionRows, map[string]interface{}{"input": uint64(uintptr(unsafe.Pointer(c.Input))), "result": resultPointer, "error": c.Failed})
	}
	for _, v := range inputs {
		inputPointers = append(inputPointers, uint64(uintptr(unsafe.Pointer(v))))
	}
	for i, v := range result {
		if v.Item != inputs[i] {
			t.Fatal("upstream item relation changed")
		}
		candidates := []int{}
		for j, original := range inputs {
			if v.Item == original {
				candidates = append(candidates, j)
			}
		}
		costCandidates := []int{}
		for j, c := range conversions {
			if !c.Failed && v.Cost == c.Reply {
				costCandidates = append(costCandidates, j)
			}
		}
		if len(costCandidates) != 1 || costCandidates[0] != i || v.Cost.Units != 14 || v.Cost.CurrencyCode != "EUR" {
			t.Fatal("upstream Cost relation or fixture value changed")
		}
		output = append(output, map[string]interface{}{"object": uint64(uintptr(unsafe.Pointer(v))), "item": uint64(uintptr(unsafe.Pointer(v.Item))), "source_candidates": candidates,
			"cost": uint64(uintptr(unsafe.Pointer(v.Cost))), "cost_source_candidates": costCandidates})
	}
	doc := map[string]interface{}{"case": name, "inputs": inputPointers, "error": err != nil, "outputs": output, "conversions": conversionRows, "kind": "independent-test-truth-not-BPF"}
	doc["call_elapsed_ns"] = callElapsed
	doc["timing_scope"] = "one prepOrderItems call including local RPCs and truth interceptor; transport connected beforehand; BPF setup and truth serialization excluded"
	data, err := json.MarshalIndent(doc, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(os.Getenv("TRACEFUSION_IDENTITY_TRUTH"), append(data, '\n'), 0644); err != nil {
		t.Fatal(err)
	}
	runtime.KeepAlive(inputs)
	runtime.KeepAlive(result)
	runtime.KeepAlive(conversions)
}

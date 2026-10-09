// Test driver and independent oracle; the original PlaceOrder and money code
// are compiled unchanged, with ordinary optimization.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"io"
	"net"
	"os"
	"sort"
	"strconv"
	"sync"
	"testing"
	"time"
)

func TestMain(m *testing.M) {
	var gate [1]byte
	if _, e := io.ReadFull(os.Stdin, gate[:]); e != nil {
		panic(e)
	}
	if e := flag.Set("test.run", "^TestOriginalPaymentPath$"); e != nil {
		panic(e)
	}
	os.Exit(m.Run())
}

type pathPeer struct {
	pb.UnimplementedProductCatalogServiceServer
	pb.UnimplementedCurrencyServiceServer
	pb.UnimplementedCartServiceServer
	pb.UnimplementedShippingServiceServer
	pb.UnimplementedPaymentServiceServer
	pb.UnimplementedEmailServiceServer
	mu                       sync.Mutex
	n, q                     int
	carry, prepFail, payFail bool
	amount                   *pb.Money
	charges                  int
}

func (p *pathPeer) GetCart(context.Context, *pb.GetCartRequest) (*pb.Cart, error) {
	items := make([]*pb.CartItem, p.n)
	for i := range items {
		items[i] = &pb.CartItem{ProductId: strconv.Itoa(i), Quantity: int32(p.q)}
	}
	return &pb.Cart{UserId: "fixture", Items: items}, nil
}
func (p *pathPeer) EmptyCart(context.Context, *pb.EmptyCartRequest) (*pb.Empty, error) {
	return &pb.Empty{}, nil
}
func (p *pathPeer) GetProduct(_ context.Context, r *pb.GetProductRequest) (*pb.Product, error) {
	if p.prepFail {
		return nil, status.Error(codes.Unavailable, "preparation fixture failure")
	}
	nanos := int32(0)
	if p.carry {
		nanos = 700000000
	}
	return &pb.Product{Id: r.Id, PriceUsd: &pb.Money{CurrencyCode: "USD", Units: 2, Nanos: nanos}}, nil
}
func (p *pathPeer) Convert(_ context.Context, r *pb.CurrencyConversionRequest) (*pb.Money, error) {
	return &pb.Money{CurrencyCode: r.ToCode, Units: r.From.Units, Nanos: r.From.Nanos}, nil
}
func (p *pathPeer) GetQuote(context.Context, *pb.GetQuoteRequest) (*pb.GetQuoteResponse, error) {
	nanos := int32(0)
	if p.carry {
		nanos = 800000000
	}
	return &pb.GetQuoteResponse{CostUsd: &pb.Money{CurrencyCode: "USD", Units: 1, Nanos: nanos}}, nil
}
func (p *pathPeer) ShipOrder(context.Context, *pb.ShipOrderRequest) (*pb.ShipOrderResponse, error) {
	return &pb.ShipOrderResponse{TrackingId: "fixture-shipment"}, nil
}
func (p *pathPeer) Charge(_ context.Context, r *pb.ChargeRequest) (*pb.ChargeResponse, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.charges++
	p.amount = &pb.Money{CurrencyCode: r.Amount.CurrencyCode, Units: r.Amount.Units, Nanos: r.Amount.Nanos}
	if p.payFail {
		return nil, status.Error(codes.Unavailable, "payment fixture failure")
	}
	return &pb.ChargeResponse{TransactionId: "fixture-payment"}, nil
}
func (p *pathPeer) SendOrderConfirmation(context.Context, *pb.SendOrderConfirmationRequest) (*pb.Empty, error) {
	return &pb.Empty{}, nil
}

func TestOriginalPaymentPath(t *testing.T) {
	name := os.Getenv("TRACEFUSION_IDENTITY_CASE")
	// This manifest is supplied to the test driver only, never to inference.
	var c struct {
		Name                                      string
		Items, Quantity                           int
		Carry, PreparationFailure, PaymentFailure bool
	}
	if e := json.Unmarshal([]byte(os.Getenv("TRACEFUSION_PAYMENT_CASE")), &c); e != nil {
		t.Fatal(e)
	}
	if c.Name != name || c.Items < 0 || c.Items > 32 || c.Quantity < 1 {
		t.Fatal("invalid fixture")
	}
	p := &pathPeer{n: c.Items, q: c.Quantity, carry: c.Carry, prepFail: c.PreparationFailure, payFail: c.PaymentFailure}
	l, e := net.Listen("tcp", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	s := grpc.NewServer()
	pb.RegisterCartServiceServer(s, p)
	pb.RegisterProductCatalogServiceServer(s, p)
	pb.RegisterCurrencyServiceServer(s, p)
	pb.RegisterShippingServiceServer(s, p)
	pb.RegisterPaymentServiceServer(s, p)
	pb.RegisterEmailServiceServer(s, p)
	go s.Serve(l)
	defer s.Stop()
	conn, e := grpc.NewClient(l.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if e != nil {
		t.Fatal(e)
	}
	defer conn.Close()
	cs := &checkoutService{cartSvcConn: conn, productCatalogSvcConn: conn, currencySvcConn: conn, shippingSvcConn: conn, paymentSvcConn: conn, emailSvcConn: conn}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	start := time.Now()
	_, e = cs.PlaceOrder(ctx, &pb.PlaceOrderRequest{UserId: "fixture", UserCurrency: "EUR", Email: "fixture@example.invalid", Address: &pb.Address{}, CreditCard: &pb.CreditCardInfo{}})
	elapsed := time.Since(start).Nanoseconds()
	if (e != nil) != (c.PreparationFailure || c.PaymentFailure) {
		t.Fatalf("unexpected PlaceOrder error: %v", e)
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	origins := map[string][]string{"Units": {}, "Nanos": {}}
	output := []int64{}
	if c.PreparationFailure {
		if p.charges != 0 {
			t.Fatal("payment after failed preparation")
		}
	} else {
		if p.charges != 1 || p.amount == nil {
			t.Fatal("missing payment")
		}
		// All fixture prices are strictly positive. In this path every Sum takes
		// the normalization arm, whose Units depends on both numeric fields and
		// whose Nanos depends on Nanos. This independent positive-case oracle
		// does not inspect the observer's plan, events, or disassembly.
		for i := -1; i < c.Items; i++ {
			prefix := "shipping"
			if i >= 0 {
				prefix = fmt.Sprintf("items[%d].Cost", i)
			}
			origins["Units"] = append(origins["Units"], prefix+".Units", prefix+".Nanos")
			origins["Nanos"] = append(origins["Nanos"], prefix+".Nanos")
		}
		sort.Strings(origins["Units"])
		sort.Strings(origins["Nanos"])
		expected := int64(1000000000) + int64(c.Items*c.Quantity)*2000000000
		if c.Carry {
			expected += 800000000 + int64(c.Items*c.Quantity)*700000000
		}
		if p.amount.Units != expected/1000000000 || int64(p.amount.Nanos) != expected%1000000000 {
			t.Fatalf("wrong payment: %+v", p.amount)
		}
		output = []int64{p.amount.Units, int64(p.amount.Nanos)}
	}
	doc := map[string]interface{}{"case": name, "sink_present": !c.PreparationFailure, "application_error": e != nil, "origins": origins, "output": output, "items": c.Items, "quantity": c.Quantity, "elapsed_ns": elapsed, "oracle": "fixture-only positive-input dependency table and mock payment RPC; unavailable to inference"}
	data, e := json.MarshalIndent(doc, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(os.Getenv("TRACEFUSION_IDENTITY_TRUTH"), append(data, '\n'), 0644); e != nil {
		t.Fatal(e)
	}
}

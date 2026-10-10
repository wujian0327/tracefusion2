// Performance driver only. PlaceOrder and money code are compiled unchanged.
// The colocated gRPC peers and oracle are identical across all four policies.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/connectivity"
	"google.golang.org/grpc/credentials/insecure"
	"io"
	"net"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"sync"
	"syscall"
	"testing"
	"time"
)

func TestMain(m *testing.M) {
	performanceGate('x') // BPF is installed before any business request.
	if err := flag.Set("test.run", "^TestPaymentPerformance$"); err != nil { panic(err) }
	os.Exit(m.Run())
}

func performanceGate(want byte) {
	var b [1]byte
	if _, err := io.ReadFull(os.Stdin, b[:]); err != nil { panic(err) }
	if b[0] != want { panic("invalid benchmark phase gate") }
}

func performanceSave(name string, value interface{}) {
	b, err := json.Marshal(value)
	if err != nil { panic(err) }
	path := filepath.Join(os.Getenv("TRACEFUSION_PERFORMANCE_OUT"), name)
	if err := os.WriteFile(path+".tmp", append(b, '\n'), 0600); err != nil { panic(err) }
	if err := os.Rename(path+".tmp", path); err != nil { panic(err) }
}

func performanceCPU() map[string]int64 {
	var r syscall.Rusage
	if err := syscall.Getrusage(syscall.RUSAGE_SELF, &r); err != nil { panic(err) }
	return map[string]int64{"user_us": r.Utime.Sec*1000000+r.Utime.Usec, "system_us": r.Stime.Sec*1000000+r.Stime.Usec}
}

type performancePeer struct {
	pb.UnimplementedProductCatalogServiceServer
	pb.UnimplementedCurrencyServiceServer
	pb.UnimplementedCartServiceServer
	pb.UnimplementedShippingServiceServer
	pb.UnimplementedPaymentServiceServer
	pb.UnimplementedEmailServiceServer
	mu sync.Mutex
	charges int
	amount *pb.Money
}

func (p *performancePeer) GetCart(context.Context, *pb.GetCartRequest) (*pb.Cart, error) {
	items := make([]*pb.CartItem, 8)
	for i := range items { items[i] = &pb.CartItem{ProductId: strconv.Itoa(i), Quantity: 2} }
	return &pb.Cart{UserId: "fixture", Items: items}, nil
}
func (p *performancePeer) EmptyCart(context.Context, *pb.EmptyCartRequest) (*pb.Empty, error) { return &pb.Empty{}, nil }
func (p *performancePeer) GetProduct(_ context.Context, r *pb.GetProductRequest) (*pb.Product, error) {
	return &pb.Product{Id: r.Id, PriceUsd: &pb.Money{CurrencyCode: "USD", Units: 2}}, nil
}
func (p *performancePeer) Convert(_ context.Context, r *pb.CurrencyConversionRequest) (*pb.Money, error) {
	return &pb.Money{CurrencyCode: r.ToCode, Units: r.From.Units, Nanos: r.From.Nanos}, nil
}
func (p *performancePeer) GetQuote(context.Context, *pb.GetQuoteRequest) (*pb.GetQuoteResponse, error) {
	return &pb.GetQuoteResponse{CostUsd: &pb.Money{CurrencyCode: "USD", Units: 1}}, nil
}
func (p *performancePeer) ShipOrder(context.Context, *pb.ShipOrderRequest) (*pb.ShipOrderResponse, error) {
	return &pb.ShipOrderResponse{TrackingId: "fixture-shipment"}, nil
}
func (p *performancePeer) Charge(_ context.Context, r *pb.ChargeRequest) (*pb.ChargeResponse, error) {
	p.mu.Lock(); defer p.mu.Unlock()
	p.charges++
	p.amount = &pb.Money{CurrencyCode: r.Amount.CurrencyCode, Units: r.Amount.Units, Nanos: r.Amount.Nanos}
	return &pb.ChargeResponse{TransactionId: "fixture-payment"}, nil
}
func (p *performancePeer) SendOrderConfirmation(context.Context, *pb.SendOrderConfirmationRequest) (*pb.Empty, error) { return &pb.Empty{}, nil }

func TestPaymentPerformance(t *testing.T) {
	warmups, err := strconv.Atoi(os.Getenv("TRACEFUSION_PERFORMANCE_WARMUPS"))
	if err != nil || warmups < 1 { t.Fatal("invalid warmup count") }
	requests, err := strconv.Atoi(os.Getenv("TRACEFUSION_PERFORMANCE_REQUESTS"))
	if err != nil || requests < 1 { t.Fatal("invalid measured count") }
	p := &performancePeer{}
	l, err := net.Listen("tcp", "127.0.0.1:0"); if err != nil { t.Fatal(err) }
	s := grpc.NewServer()
	pb.RegisterCartServiceServer(s,p); pb.RegisterProductCatalogServiceServer(s,p)
	pb.RegisterCurrencyServiceServer(s,p); pb.RegisterShippingServiceServer(s,p)
	pb.RegisterPaymentServiceServer(s,p); pb.RegisterEmailServiceServer(s,p)
	go s.Serve(l); defer s.Stop()
	conn, err := grpc.NewClient(l.Addr().String(),grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil { t.Fatal(err) }; defer conn.Close()
	ready, cancel := context.WithTimeout(context.Background(),30*time.Second)
	conn.Connect()
	for state := conn.GetState(); state != connectivity.Ready; state = conn.GetState() {
		if !conn.WaitForStateChange(ready,state) { cancel(); t.Fatal("gRPC not ready") }
	}
	cancel()
	cs := &checkoutService{cartSvcConn:conn,productCatalogSvcConn:conn,currencySvcConn:conn,shippingSvcConn:conn,paymentSvcConn:conn,emailSvcConn:conn}
	req := &pb.PlaceOrderRequest{UserId:"fixture",UserCurrency:"EUR",Email:"fixture@example.invalid",Address:&pb.Address{},CreditCard:&pb.CreditCardInfo{}}
	invoke := func(index int) int64 {
		ctx, cancel := context.WithTimeout(context.Background(),30*time.Second)
		start := time.Now()
		_, err := cs.PlaceOrder(ctx,req)
		elapsed := time.Since(start).Nanoseconds()
		cancel()
		if err != nil { t.Fatalf("request %d: %v",index,err) }
		p.mu.Lock()
		ok := p.charges==index+1 && p.amount!=nil && p.amount.CurrencyCode=="EUR" && p.amount.Units==33 && p.amount.Nanos==0
		p.mu.Unlock()
		if !ok { t.Fatalf("independent payment check failed: %d",index) }
		return elapsed
	}
	for i:=0;i<warmups;i++ { invoke(i) }
	performanceSave("warmup.done",map[string]int{"requests":warmups})
	performanceGate('m') // Same ready process/connections after warmup.
	latencies := make([]int64,requests)
	cpuStart := performanceCPU()
	start := time.Now()
	for i:=0;i<requests;i++ { latencies[i]=invoke(warmups+i) }
	wall := time.Since(start).Nanoseconds()
	cpuEnd := performanceCPU()
	performanceSave("measure.done",map[string]int{"requests":requests})
	performanceGate('q') // Export only after the observer's measured interval.
	performanceSave("measurements.json",map[string]interface{}{"warmups":warmups,"requests":requests,"latency_ns":latencies,"wall_ns":wall,"cpu_start":cpuStart,"cpu_end":cpuEnd,"scope":"PlaceOrder latency; process CPU includes colocated mock peers and common harness checks; no trace SDK added"})
	// Positive fixed inputs: normalization reads Units and Nanos even when Nanos=0.
	// This table uses neither observed events nor the binary dependency model.
	origins := map[string][]string{"Units":{},"Nanos":{}}
	for i:=-1;i<8;i++ {
		prefix:="shipping"; if i>=0 { prefix=fmt.Sprintf("items[%d].Cost",i) }
		origins["Units"]=append(origins["Units"],prefix+".Units",prefix+".Nanos")
		origins["Nanos"]=append(origins["Nanos"],prefix+".Nanos")
	}
	sort.Strings(origins["Units"]);sort.Strings(origins["Nanos"])
	performanceSave("truth.json",map[string]interface{}{"sink_present":true,"application_error":false,"origins":origins,"output":[]int64{33,0},"warmups":warmups,"requests":requests,"oracle":"fixed positive-input table and separately checked mock payment RPC; unavailable to inference"})
}

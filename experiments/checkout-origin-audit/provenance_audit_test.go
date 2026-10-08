// Test-only fixture for upstream Online Boutique v0.10.4. It calls the original
// checkout method; local gRPC peers and interceptors provide audit ground truth.
// These observations are NOT produced by TraceFusion or eBPF.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"sync"
	"testing"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

type auditRPC struct {
	Kind    string
	TraceID string
	Failed  bool
}
type auditPeer struct {
	pb.UnimplementedProductCatalogServiceServer
	pb.UnimplementedCurrencyServiceServer
	mu     sync.Mutex
	calls  []auditRPC
	fail   string
	failAt int
	counts map[string]int
}

func (s *auditPeer) record(ctx context.Context, kind string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	i := s.counts[kind]
	s.counts[kind]++
	failed := s.fail == kind && i == s.failAt
	s.calls = append(s.calls, auditRPC{kind, trace.SpanContextFromContext(ctx).TraceID().String(), failed})
	return failed
}
func (s *auditPeer) GetProduct(ctx context.Context, r *pb.GetProductRequest) (*pb.Product, error) {
	if s.record(ctx, "product") {
		return nil, status.Error(codes.Unavailable, "audit failure")
	}
	return &pb.Product{Id: r.Id, PriceUsd: &pb.Money{CurrencyCode: "USD", Units: 7}}, nil
}
func (s *auditPeer) Convert(ctx context.Context, r *pb.CurrencyConversionRequest) (*pb.Money, error) {
	if s.record(ctx, "currency") {
		return nil, status.Error(codes.Unavailable, "audit failure")
	}
	// A mock conversion for this test, not a summary inferred for the real service.
	return &pb.Money{CurrencyCode: r.ToCode, Units: r.From.Units * 2, Nanos: r.From.Nanos}, nil
}

type auditBoundary struct {
	Method         string
	Request, Reply interface{}
	Failed         bool
}
type auditCase struct {
	Name                         string `json:"name"`
	InputItems                   int    `json:"input_items"`
	OutputItems                  int    `json:"output_items"`
	Error                        bool   `json:"error"`
	ProductCalls                 int    `json:"product_calls"`
	CurrencyCalls                int    `json:"currency_calls"`
	ProductSameRoot              int    `json:"product_same_root"`
	CurrencySameRoot             int    `json:"currency_same_root"`
	BoundaryIdentityChecks       int    `json:"boundary_identity_checks"`
	EqualValuesDistinctInstances bool   `json:"equal_values_distinct_instances"`
}

func TestTraceFusionRealCheckoutAudit(t *testing.T) {
	oldProvider := otel.GetTracerProvider()
	oldProp := otel.GetTextMapPropagator()
	provider := sdktrace.NewTracerProvider(sdktrace.WithSampler(sdktrace.AlwaysSample()))
	otel.SetTracerProvider(provider)
	otel.SetTextMapPropagator(propagation.TraceContext{})
	defer func() {
		provider.Shutdown(context.Background())
		otel.SetTracerProvider(oldProvider)
		otel.SetTextMapPropagator(oldProp)
	}()
	rows := []auditCase{}
	cases := []struct {
		name string
		n    int
		fail string
		at   int
	}{
		{"empty", 0, "", 0}, {"one", 1, "", 0}, {"equal-eight", 8, "", 0}, {"equal-thirty-two", 32, "", 0},
		{"product-error-second", 4, "product", 1}, {"currency-error-second", 4, "currency", 1},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			peer := &auditPeer{fail: tc.fail, failAt: tc.at, counts: map[string]int{}}
			listener, err := net.Listen("tcp", "127.0.0.1:0")
			if err != nil {
				t.Fatal(err)
			}
			server := grpc.NewServer(grpc.StatsHandler(otelgrpc.NewServerHandler()))
			pb.RegisterProductCatalogServiceServer(server, peer)
			pb.RegisterCurrencyServiceServer(server, peer)
			go server.Serve(listener)
			defer server.Stop()
			var mu sync.Mutex
			boundaries := []auditBoundary{}
			interceptor := func(ctx context.Context, method string, req, reply interface{}, cc *grpc.ClientConn, invoke grpc.UnaryInvoker, opts ...grpc.CallOption) error {
				err := invoke(ctx, method, req, reply, cc, opts...)
				mu.Lock()
				boundaries = append(boundaries, auditBoundary{method, req, reply, err != nil})
				mu.Unlock()
				return err
			}
			conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()),
				grpc.WithStatsHandler(otelgrpc.NewClientHandler()), grpc.WithUnaryInterceptor(interceptor))
			if err != nil {
				t.Fatal(err)
			}
			defer conn.Close()
			service := &checkoutService{productCatalogSvcConn: conn, currencySvcConn: conn}
			items := make([]*pb.CartItem, tc.n)
			for i := range items {
				items[i] = &pb.CartItem{ProductId: "same-product", Quantity: 2}
			}
			ctx, span := otel.Tracer("audit").Start(context.Background(), "prepOrderItems")
			root := span.SpanContext().TraceID().String()
			result, err := service.prepOrderItems(ctx, items, "EUR")
			span.End()
			row := auditCase{Name: tc.name, InputItems: tc.n, OutputItems: len(result), Error: err != nil}
			if (err != nil) != (tc.fail != "") {
				t.Fatalf("unexpected error: %v", err)
			}
			products := []*pb.Product{}
			conversions := []auditBoundary{}
			for _, b := range boundaries {
				if b.Failed {
					continue
				}
				switch reply := b.Reply.(type) {
				case *pb.Product:
					products = append(products, reply)
				case *pb.Money:
					conversions = append(conversions, b)
				}
			}
			peer.mu.Lock()
			for _, c := range peer.calls {
				if c.Kind == "product" {
					row.ProductCalls++
					if c.TraceID == root {
						row.ProductSameRoot++
					}
				}
				if c.Kind == "currency" {
					row.CurrencyCalls++
					if c.TraceID == root {
						row.CurrencySameRoot++
					}
				}
			}
			peer.mu.Unlock()
			if row.ProductSameRoot != row.ProductCalls || row.CurrencySameRoot != 0 {
				t.Fatalf("trace context expectation changed: %+v", row)
			}
			if err != nil {
				if result != nil {
					t.Fatal("partial result escaped on an error")
				}
				expectedCurrency := tc.at
				if tc.fail == "currency" {
					expectedCurrency++
				}
				if row.ProductCalls != tc.at+1 || row.CurrencyCalls != expectedCurrency {
					t.Fatal("unexpected error-path RPC count")
				}
			} else {
				if len(result) != tc.n || row.ProductCalls != tc.n || row.CurrencyCalls != tc.n {
					t.Fatal("unexpected success counts")
				}
				seen := map[*pb.Money]bool{}
				for i, item := range result {
					conversion := conversions[i]
					request := conversion.Request.(*pb.CurrencyConversionRequest)
					price := conversion.Reply.(*pb.Money)
					if item.Item != items[i] || item.Cost != price || request.From != products[i].PriceUsd {
						t.Fatal("boundary object association changed")
					}
					if item.Item.Quantity != 2 || price.Units != 14 || price.CurrencyCode != "EUR" {
						t.Fatal("unexpected data")
					}
					if seen[price] {
						t.Fatal("different conversion instances reused a result object")
					}
					seen[price] = true
					row.BoundaryIdentityChecks += 3
				}
				row.EqualValuesDistinctInstances = tc.n > 1 && len(seen) == tc.n
			}
			rows = append(rows, row)
		})
	}
	if t.Failed() {
		return
	}
	report := map[string]interface{}{"cases": rows, "all_passed": true, "production_function_modified": false,
		"capture":      "test-only gRPC interceptors and server trace contexts; not eBPF",
		"remote_peers": "local mock ProductCatalog and Currency peers, not full application deployment",
		"claim":        "Validate boundary evidence needs and source structure, not TraceFusion provenance coverage"}
	data, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if path := os.Getenv("TRACEFUSION_AUDIT_REPORT"); path != "" {
		if err = os.WriteFile(path, append(data, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
	fmt.Println(string(data))
}

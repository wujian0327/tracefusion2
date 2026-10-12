// Original prepOrderItems consumer. Currency mock is outside the target scope.
package main

import (
	"context"
	"encoding/json"
	"net"
	"os"
	"sync"
	"testing"
	"time"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/otel"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type rq1Case struct {
	Name       string   `json:"name"`
	IDs        []string `json:"ids"`
	Concurrent bool     `json:"concurrent"`
}
type rq1Currency struct {
	pb.UnimplementedCurrencyServiceServer
}

func (*rq1Currency) Convert(_ context.Context, r *pb.CurrencyConversionRequest) (*pb.Money, error) {
	return &pb.Money{CurrencyCode: r.ToCode, Units: r.From.Units, Nanos: r.From.Nanos}, nil
}
func TestRQ1CheckoutClient(t *testing.T) {
	log, provider, err := rq1Open("checkout")
	if err != nil {
		t.Fatal(err)
	}
	defer log.f.Close()
	defer provider.Shutdown(context.Background())
	data, err := os.ReadFile(os.Getenv("RQ1_CASES"))
	if err != nil {
		t.Fatal(err)
	}
	var cases []rq1Case
	if err = json.Unmarshal(data, &cases); err != nil {
		t.Fatal(err)
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	currency := grpc.NewServer(grpc.StatsHandler(&rq1Stats{otelgrpc.NewServerHandler(), log}))
	pb.RegisterCurrencyServiceServer(currency, &rq1Currency{})
	go currency.Serve(listener)
	defer currency.Stop()
	run := func(c rq1Case) {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		ctx, root := otel.Tracer("tracefusion.rq1.workload").Start(ctx, c.Name)
		defer root.End()
		log.write(map[string]any{"kind": "case_begin", "case": c.Name, "ids": c.IDs, "context": rq1Context(ctx)})
		ordinal := 0
		audit := func(callCtx context.Context, method string, req, reply any, cc *grpc.ClientConn, invoke grpc.UnaryInvoker, opts ...grpc.CallOption) error {
			if method == "/hipstershop.CurrencyService/Convert" {
				r := req.(*pb.CurrencyConversionRequest)
				log.write(map[string]any{"kind": "target", "case": c.Name, "ordinal": ordinal - 1, "context": rq1Context(callCtx),
					"message": log.message(r), "from_pointer": rq1Pointer(r.From)})
			}
			e := invoke(callCtx, method, req, reply, cc, opts...)
			if method == "/hipstershop.ProductCatalogService/GetProduct" {
				row := map[string]any{"kind": "product_reply", "case": c.Name, "ordinal": ordinal, "failed": e != nil,
					"context": rq1Context(callCtx), "requested_id": req.(*pb.GetProductRequest).Id}
				if e == nil {
					p := reply.(*pb.Product)
					row["message"] = log.message(p)
					row["price_pointer"] = rq1Pointer(p.PriceUsd)
				}
				log.write(row)
				ordinal++
			}
			return e
		}
		connect := func(address string) *grpc.ClientConn {
			cc, e := grpc.NewClient(address, grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithUnaryInterceptor(audit),
				grpc.WithStatsHandler(&rq1Stats{otelgrpc.NewClientHandler(), log}))
			if e != nil {
				t.Error(e)
				return nil
			}
			return cc
		}
		pc := connect(os.Getenv("RQ1_CATALOG_ADDR"))
		if pc == nil {
			return
		}
		defer pc.Close()
		cur := connect(listener.Addr().String())
		if cur == nil {
			return
		}
		defer cur.Close()
		svc := &checkoutService{productCatalogSvcConn: pc, currencySvcConn: cur}
		items := make([]*pb.CartItem, len(c.IDs))
		for i, id := range c.IDs {
			items[i] = &pb.CartItem{ProductId: id, Quantity: 2}
		}
		out, e := svc.prepOrderItems(ctx, items, "EUR") // Actual unmodified upstream method.
		log.write(map[string]any{"kind": "case_end", "case": c.Name, "failed": e != nil, "output_items": len(out), "context": rq1Context(ctx)})
	}
	for _, c := range cases {
		if !c.Concurrent {
			run(c)
		}
	}
	var wg sync.WaitGroup
	for _, c := range cases {
		if c.Concurrent {
			wg.Add(1)
			go func(c rq1Case) { defer wg.Done(); run(c) }(c)
		}
	}
	wg.Wait()
	currency.GracefulStop()
	log.write(map[string]any{"kind": "finish", "success": !t.Failed()})
}

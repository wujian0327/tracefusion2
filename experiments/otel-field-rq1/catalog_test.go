// Driver around original productCatalog.GetProduct and original catalog loader.
package main

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"os"
	"testing"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/productcatalogservice/genproto"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"
)

func TestRQ1CatalogServer(t *testing.T) {
	log, provider, err := rq1Open("productcatalog")
	if err != nil {
		t.Fatal(err)
	}
	defer log.f.Close()
	defer provider.Shutdown(context.Background())
	svc := &productCatalog{}
	if err = loadCatalog(&svc.catalog); err != nil {
		t.Fatal(err)
	}
	log.write(map[string]any{"kind": "catalog", "message": log.message(&svc.catalog)})
	for i, p := range svc.catalog.Products {
		log.write(map[string]any{"kind": "catalog_record", "index": i, "message": log.message(p), "price_pointer": rq1Pointer(p.PriceUsd)})
	}
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	audit := func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		reply, e := handler(ctx, req) // Actual unmodified upstream handler.
		row := map[string]any{"kind": "handler_return", "method": info.FullMethod, "context": rq1Context(ctx), "failed": e != nil}
		if e == nil {
			p := reply.(*pb.Product)
			row["message"] = log.message(p)
			row["price_pointer"] = rq1Pointer(p.PriceUsd)
		}
		log.write(row)
		return reply, e
	}
	server := grpc.NewServer(grpc.StatsHandler(&rq1Stats{otelgrpc.NewServerHandler(), log}), grpc.UnaryInterceptor(audit))
	pb.RegisterProductCatalogServiceServer(server, svc)
	go server.Serve(l)
	defer server.Stop()
	ready, _ := json.Marshal(map[string]any{"address": l.Addr().String(), "pid": os.Getpid()})
	if err = os.WriteFile(os.Getenv("RQ1_READY"), ready, 0644); err != nil {
		t.Fatal(err)
	}
	var stop [1]byte
	if _, err = io.ReadFull(os.Stdin, stop[:]); err != nil {
		t.Fatal(err)
	}
	server.GracefulStop()
	log.write(map[string]any{"kind": "catalog_end", "message": log.message(&svc.catalog)})
	log.write(map[string]any{"kind": "finish", "success": true})
}

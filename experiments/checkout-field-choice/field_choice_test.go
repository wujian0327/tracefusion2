// Controlled variant; chooseUnits is NOT original Online Boutique business code.
package main

import (
	"context"
	"encoding/json"
	"flag"
	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"io"
	"net"
	"os"
	"runtime"
	"strings"
	"testing"
	"unsafe"
)

// An ordinary function value retains a separately callable optimized function;
// no noinline directive or disabled compiler optimization is used.
var fieldSelector = chooseUnits
var overwriteSelector = overwriteUnits

// Both conditions and all field stores survive the pinned optimized build.
// The first choice is killed by the final full-field assignment on both arms.
func overwriteUnits(a, b *pb.Money, firstB, finalB bool) *pb.Money {
	out := &pb.Money{CurrencyCode: "EUR"}
	out.Units = a.Units
	if firstB {
		out.Units = b.Units
	}
	if finalB {
		out.Units = b.Units
	} else {
		out.Units = a.Units
	}
	return out
}

func chooseUnits(a, b *pb.Money, useB bool) *pb.Money {
	out := &pb.Money{CurrencyCode: "EUR"}
	units := a.Units
	if useB {
		units = b.Units
	}
	out.Units = units
	return out
}

func TestMain(m *testing.M) {
	var gate [1]byte
	if _, err := io.ReadFull(os.Stdin, gate[:]); err != nil {
		panic(err)
	}
	if err := flag.Set("test.run", "^TestFieldChoice$"); err != nil {
		panic(err)
	}
	os.Exit(m.Run())
}

type choicePeer struct {
	pb.UnimplementedCurrencyServiceServer
}

func (*choicePeer) Convert(ctx context.Context, r *pb.CurrencyConversionRequest) (*pb.Money, error) {
	return &pb.Money{CurrencyCode: r.ToCode, Units: r.From.Units * 2}, nil
}

func TestFieldChoice(t *testing.T) {
	name := os.Getenv("TRACEFUSION_IDENTITY_CASE")
	overwrite := os.Getenv("TRACEFUSION_FIELD_VARIANT") == "overwrite"
	firstB := false
	useB, different := false, false
	if overwrite {
		parts := strings.Split(name, "-")
		if len(parts) != 2 || (parts[0] != "equal" && parts[0] != "different") ||
			(parts[1] != "aa" && parts[1] != "ab" && parts[1] != "ba" && parts[1] != "bb") {
			t.Fatal("unknown overwrite case", name)
		}
		different = parts[0] == "different"
		firstB, useB = parts[1][0] == 'b', parts[1][1] == 'b'
	} else {
		switch name {
		case "equal-a":
		case "equal-b":
			useB = true
		case "different-a":
			different = true
		case "different-b":
			different = true
			useB = true
		default:
			t.Fatal("unknown case", name)
		}
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := grpc.NewServer()
	pb.RegisterCurrencyServiceServer(server, &choicePeer{})
	go server.Serve(listener)
	defer server.Stop()
	conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	service := &checkoutService{currencySvcConn: conn}
	a, err := service.convertCurrency(context.Background(), &pb.Money{CurrencyCode: "USD", Units: 7}, "EUR")
	if err != nil {
		t.Fatal(err)
	}
	bInput := int64(7)
	if different {
		bInput = 19
	}
	b, err := service.convertCurrency(context.Background(), &pb.Money{CurrencyCode: "USD", Units: bInput}, "EUR")
	if err != nil {
		t.Fatal(err)
	}
	if a == b {
		t.Fatal("RPC replies must be distinct live objects")
	}
	var result *pb.Money
	if overwrite {
		result = overwriteSelector(a, b, firstB, useB)
	} else {
		result = fieldSelector(a, b, useB)
	}
	expected, index := a, 0
	if useB {
		expected = b
		index = 1
	}
	if result == a || result == b || result.Units != expected.Units || result.CurrencyCode != "EUR" {
		t.Fatal("fixture result differs")
	}
	ptr := func(v *pb.Money) uint64 { return uint64(uintptr(unsafe.Pointer(v))) }
	truth := map[string]interface{}{"case": name, "input_objects": []uint64{ptr(a), ptr(b)},
		"input_values": []int64{a.Units, b.Units}, "output_object": ptr(result), "output_value": result.Units,
		"source_candidates": []int{index}, "source_field_address": uint64(uintptr(unsafe.Pointer(&expected.Units))),
		"scope": "independent fixture truth; one immutable Units field copy into a fresh object"}
	data, err := json.MarshalIndent(truth, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(os.Getenv("TRACEFUSION_IDENTITY_TRUTH"), append(data, '\n'), 0644); err != nil {
		t.Fatal(err)
	}
	runtime.KeepAlive(a)
	runtime.KeepAlive(b)
	runtime.KeepAlive(result)
}

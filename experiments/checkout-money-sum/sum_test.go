// Calls the unmodified upstream money.Sum exactly once; truth is fixture-only.
package main

import (
	"encoding/json"
	"flag"
	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/money"
	"io"
	"os"
	"testing"
)

func TestMain(m *testing.M) {
	var gate [1]byte
	if _, err := io.ReadFull(os.Stdin, gate[:]); err != nil {
		panic(err)
	}
	if err := flag.Set("test.run", "^TestOriginalSum$"); err != nil {
		panic(err)
	}
	os.Exit(m.Run())
}

func TestOriginalSum(t *testing.T) {
	type example struct {
		lu         int64
		ln         int32
		ru         int64
		rn         int32
		ou         int64
		on         int32
		normalized bool
		err        bool
		currency   string
	}
	cases := map[string]example{
		"equal-positive":    {1, 200000000, 1, 200000000, 2, 400000000, true, false, "EUR"},
		"carry":             {1, 800000000, 2, 700000000, 4, 500000000, true, false, "EUR"},
		"negative-carry":    {-1, -800000000, -2, -700000000, -4, -500000000, true, false, "EUR"},
		"adjust-positive":   {2, 100000000, -1, -300000000, 0, 800000000, false, false, "EUR"},
		"adjust-negative":   {-2, -100000000, 1, 300000000, 0, -800000000, false, false, "EUR"},
		"cancel":            {1, 100000000, -1, -100000000, 0, 0, true, false, "EUR"},
		"zero":              {0, 0, 0, 0, 0, 0, true, false, "EUR"},
		"invalid-nanos":     {1, 1000000000, 1, 0, 0, 0, false, true, "EUR"},
		"invalid-sign":      {1, -1, 1, 0, 0, 0, false, true, "EUR"},
		"currency-mismatch": {1, 0, 1, 0, 0, 0, false, true, "USD"},
	}
	name := os.Getenv("TRACEFUSION_IDENTITY_CASE")
	c, ok := cases[name]
	if !ok {
		t.Fatal("unknown case", name)
	}
	l := pb.Money{CurrencyCode: "EUR", Units: c.lu, Nanos: c.ln}
	r := pb.Money{CurrencyCode: c.currency, Units: c.ru, Nanos: c.rn}
	result, err := money.Sum(l, r)
	if (err != nil) != c.err || result.Units != c.ou || result.Nanos != c.on {
		t.Fatalf("unexpected original Sum result: %+v, %v", result, err)
	}
	units := []string{"l.Units", "r.Units"}
	nanos := []string{"l.Nanos", "r.Nanos"}
	if c.normalized {
		units = []string{"l.Nanos", "l.Units", "r.Nanos", "r.Units"}
	}
	if c.err {
		units = []string{}
		nanos = []string{}
	}
	truth := map[string]interface{}{
		"case": name, "inputs": []int64{c.lu, int64(c.ln), c.ru, int64(c.rn)},
		"output": []int64{result.Units, int64(result.Nanos)}, "error": err != nil,
		"origins": map[string]interface{}{"Units": units, "Nanos": nanos},
		"scope":   "independent case table: executed data dependencies, excluding implicit control dependencies",
	}
	data, err := json.MarshalIndent(truth, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(os.Getenv("TRACEFUSION_IDENTITY_TRUTH"), append(data, '\n'), 0644); err != nil {
		t.Fatal(err)
	}
}

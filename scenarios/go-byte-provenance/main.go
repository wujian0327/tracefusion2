package main

import (
 "encoding/json"
 "fmt"
 "os"
 "runtime"
)

type request struct {
 A, B, C string
 UseC bool
}

func readValue(path string) *[4]byte {
 b, err := os.ReadFile(path)
 if err != nil { panic(err) }
 if len(b) != 4 { panic("requires exactly four bytes") }
 value := new([4]byte)
 copy(value[:], b)
 return value
}

func marshalResult(value *[4]byte) []byte {
 b, err := json.Marshal(struct { Result string `json:"result"` }{string(value[:])})
 if err != nil { panic(err) }
 return b
}

func run(aPath, bPath, cPath string, useC bool) []byte {
 a := readValue(aPath)
 b := readValue(bPath)
 c := readValue(cPath)
 selected := a
 if useC { selected = c }
 output := new([4]byte)
 transform(output, selected, b)
 encoded := marshalResult(output)
 runtime.KeepAlive(a)
 runtime.KeepAlive(b)
 runtime.KeepAlive(c)
 return encoded
}

func main() {
 var in request
 if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil { panic(err) }
 fmt.Println(string(run(in.A, in.B, in.C, in.UseC)))
}

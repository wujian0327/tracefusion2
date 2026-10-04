package main

import (
 "encoding/json"
 "fmt"
 "os"
 "runtime"
)

type request struct { Phone, Prefix, Other string }

// These are ordinary application operations, without provenance IDs/callbacks.
func readValue(path string) string {
 b, err := os.ReadFile(path)
 if err != nil { panic(err) }
 return string(b)
}

func marshalResult(value string) []byte {
 b, err := json.Marshal(struct { Result string `json:"result"` }{value})
 if err != nil { panic(err) }
 return b
}

func run(phonePath, prefixPath, otherPath string) []byte {
 phone := readValue(phonePath)
 prefix := readValue(prefixPath)
 other := readValue(otherPath)
 result := prefix + phone
 encoded := marshalResult(result)
 runtime.KeepAlive(phone)
 runtime.KeepAlive(prefix)
 runtime.KeepAlive(other)
 return encoded
}

func main() {
 var in request
 if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil { panic(err) }
 encoded := run(in.Phone, in.Prefix, in.Other)
 fmt.Println(string(encoded))
}

package main

import (
	"encoding/json"
	"os"
	"runtime"
	"syscall"
)

func main() {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	if len(os.Args) == 2 && os.Args[1] == "--wait" {
		if err := syscall.Kill(os.Getpid(), syscall.SIGSTOP); err != nil { panic(err) }
	}
	functions := []func(*output, *input, uint32){goCallSelect, goCallOverwrite, goCallMerge}
	names := []string{"main.goCallSelect", "main.goCallOverwrite", "main.goCallMerge"}
	encoder := json.NewEncoder(os.Stdout)
	sequence := 0
	for round := uint32(0); round < 2; round++ {
		src := input{424242+round, 424242+round, 99}
		for f, function := range functions {
			for choose := uint32(0); choose < 2; choose++ {
				dst := output{0xdeadbeef, 0}
				function(&dst, &src, choose)
				// Independent harness truth; the inference core never reads it.
				expected := src.public_value ^ 0x55
				sources := []string{"input.public_value"}
				if f == 0 && choose != 0 {
					expected = src.secret ^ 0x55
					sources = []string{"input.secret"}
				} else if f == 1 {
					expected = src.public_value
				} else if f == 2 {
					expected = (src.secret ^ 0x55) + src.public_value
					sources = []string{"input.secret", "input.public_value"}
				}
				sequence++
				if err := encoder.Encode(map[string]interface{}{
					"sequence": sequence, "function": names[f], "select": choose,
					"expected_sources": sources, "expected_value": expected, "output": dst.value,
				}); err != nil { panic(err) }
			}
		}
	}
}

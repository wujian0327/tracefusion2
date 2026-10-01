package main

import (
	"encoding/json"
	"os"
	"runtime"
	"syscall"
)

func main() {
	// Explicit experimental restriction: the observed user goroutine stays
	// on one OS thread. This does not claim general scheduler support.
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	if len(os.Args) == 2 && os.Args[1] == "--wait" {
		if err := syscall.Kill(os.Getpid(), syscall.SIGSTOP); err != nil { panic(err) }
	}
	functions := []func(*output, *input, uint32){goSelect, goOverwrite, goMerge}
	names := []string{"main.goSelect", "main.goOverwrite", "main.goMerge"}
	encoder := json.NewEncoder(os.Stdout)
	sequence := 0
	for round := uint32(0); round < 2; round++ {
		src := input{424242+round, 424242+round, 99}
		for f, function := range functions {
			for choose := uint32(0); choose < 2; choose++ {
				dst := output{0xdeadbeef, 0}
				function(&dst, &src, choose)
				expected := src.public_value
				sources := []string{"input.public_value"}
				if f == 0 && choose != 0 {
					expected = src.secret ^ 0x55
					sources = []string{"input.secret"}
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

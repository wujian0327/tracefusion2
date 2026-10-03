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
	functions := []func(*output, *input, uint32){goLoopTransform, goLoopOverwrite, goLoopAccumulate}
	names := []string{"main.goLoopTransform", "main.goLoopOverwrite", "main.goLoopAccumulate"}
	counts := []uint32{0, 1, 2, 4}
	encoder := json.NewEncoder(os.Stdout)
	sequence := 0
	for round := uint32(0); round < 2; round++ {
		src := input{424242+round, 424242+round, 99}
		for f, function := range functions {
			for _, count := range counts {
				dst := output{0xdeadbeef, 0}
				function(&dst, &src, count)
				// Harness truth uses source-level semantics, never the probe plan.
				expected := uint32(0)
				sources := []string{}
				if f == 0 {
					expected = src.secret
					for i := uint32(0); i < count; i++ { expected = (expected ^ 0x55) + 3 }
					sources = []string{"input.secret"}
				} else if f == 1 {
					expected = 42
					if count > 0 && count <= 2 {
						expected = src.secret; sources = []string{"input.secret"}
					} else if count > 2 {
						expected = src.public_value; sources = []string{"input.public_value"}
					}
				} else if count > 0 {
					secretCount := count
					if secretCount > 2 { secretCount = 2 }
					expected = secretCount*src.secret + (count-secretCount)*src.public_value
					sources = []string{"input.secret"}
					if count > 2 { sources = append(sources, "input.public_value") }
				}
				sequence++
				if err := encoder.Encode(map[string]interface{}{
					"sequence": sequence, "function": names[f], "count": count,
					"expected_sources": sources, "expected_value": expected, "output": dst.value,
				}); err != nil { panic(err) }
			}
		}
	}
}

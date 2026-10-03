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
	// Probe compilation/attachment happens while stopped. Yield after resume
	// so a pending runtime preemption is handled outside the observed roots.
	// Stack guards remain enabled; a slow path inside a root still fails.
	runtime.Gosched()
	functions := []func(*output, *input, uint32){goLoopCallOverwrite, goLoopCallAccumulate, goLoopCallTransform}
	names := []string{"main.goLoopCallOverwrite", "main.goLoopCallAccumulate", "main.goLoopCallTransform"}
	counts := []uint32{0, 1, 2, 4}
	encoder := json.NewEncoder(os.Stdout)
	sequence := 0
	for round := uint32(0); round < 2; round++ {
		src := input{424242+round, 424242+round, 99}
		for f, function := range functions {
			for _, count := range counts {
				dst := output{0xdeadbeef, 0}
				function(&dst, &src, count)
				// Independent source-level truth; never reads plan/events.
				secretCount := count
				if secretCount > 2 { secretCount = 2 }
				expected := uint32(0)
				if f == 0 {
					expected = 42
					if count > 0 && count <= 2 { expected = src.secret } else if count > 2 { expected = src.public_value }
				} else if f == 1 {
					expected = secretCount*src.secret + (count-secretCount)*src.public_value
				} else {
					expected = secretCount*(src.secret^0x55) + (count-secretCount)*(src.public_value^0x55)
				}
				sources := []string{}
				if count > 0 {
					if f == 0 && count > 2 { sources = []string{"input.public_value"} } else {
						sources = []string{"input.secret"}
						if count > 2 { sources = append(sources, "input.public_value") }
					}
				}
				helperCalls := count
				if f == 2 { helperCalls = count*2 }
				sequence++
				if err := encoder.Encode(map[string]interface{}{
					"sequence": sequence, "function": names[f], "count": count, "expected_helper_calls": helperCalls,
					"expected_sources": sources, "expected_value": expected, "output": dst.value,
				}); err != nil { panic(err) }
			}
		}
	}
}

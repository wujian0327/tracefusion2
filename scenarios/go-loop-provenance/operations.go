package main

type input struct { secret, public_value, noise uint32 }
type output struct { value, audit uint32 }

// Ordinary Go: preserve optimization; no assembly, cgo, volatile substitute,
// tracing tags, nosplit, or helper calls within these observed functions.
func goLoopTransform(dst *output, src *input, count uint32) {
	x := src.secret
	for i := uint32(0); i < count; i++ {
		x = (x ^ 0x55) + 3
	}
	dst.value = x
}

func goLoopOverwrite(dst *output, src *input, count uint32) {
	x := uint32(42)
	for i := uint32(0); i < count; i++ {
		if i < 2 { x = src.secret } else { x = src.public_value }
	}
	dst.value = x
}

func goLoopAccumulate(dst *output, src *input, count uint32) {
	x := uint32(0)
	for i := uint32(0); i < count; i++ {
		if i < 2 { x += src.secret } else { x += src.public_value }
	}
	dst.value = x
}

package main

type input struct { secret, public_value, noise uint32 }
type output struct { value, audit uint32 }

// Ordinary Go functions. Inlining is disabled by the experiment's build flag;
// there is no nosplit, cgo, assembly, tracing API or source provenance label.
func readSelected(src *input, choose uint32) uint32 {
	if choose == 0 { return src.public_value }
	return src.secret
}

func transformSelected(src *input, choose uint32) uint32 {
	return readSelected(src, choose) ^ 0x55
}

func goCallSelect(dst *output, src *input, choose uint32) {
	dst.value = transformSelected(src, choose)
}

func goCallOverwrite(dst *output, src *input, choose uint32) {
	dst.value = readSelected(src, 1)
	dst.value = readSelected(src, 0)
}

func goCallMerge(dst *output, src *input, choose uint32) {
	first := transformSelected(src, 1)
	second := readSelected(src, 0)
	dst.value = first + second
}

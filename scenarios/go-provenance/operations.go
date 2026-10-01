package main

type input struct { secret, public_value, noise uint32 }
type output struct { value, audit uint32 }

// Plain Go functions: no cgo, assembly, nosplit, tracing API or source tags.
func goSelect(dst *output, src *input, choose uint32) {
	if choose == 0 {
		dst.value = src.public_value
		return
	}
	dst.value = src.secret ^ 0x55
}

func goOverwrite(dst *output, src *input, choose uint32) {
	dst.value = src.secret
	dst.value = src.public_value
}

func goMerge(dst *output, src *input, choose uint32) {
	dst.value = (src.secret ^ 0x55) + src.public_value
}

package main

type input struct { secret, public_value, noise uint32 }
type output struct { value, audit uint32 }

func readIteration(src *input, i uint32) uint32 {
	if i < 2 { return src.secret }
	return src.public_value
}

func transformIteration(src *input, i uint32) uint32 {
	return readIteration(src, i) ^ 0x55
}

func goLoopCallOverwrite(dst *output, src *input, count uint32) {
	x := uint32(42)
	for i := uint32(0); i < count; i++ { x = readIteration(src, i) }
	dst.value = x
}

func goLoopCallAccumulate(dst *output, src *input, count uint32) {
	x := uint32(0)
	for i := uint32(0); i < count; i++ { x += readIteration(src, i) }
	dst.value = x
}

func goLoopCallTransform(dst *output, src *input, count uint32) {
	x := uint32(0)
	for i := uint32(0); i < count; i++ { x += transformIteration(src, i) }
	dst.value = x
}

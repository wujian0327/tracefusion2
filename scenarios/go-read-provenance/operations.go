package main

type input struct { left, right, noise uint32 }
type output struct { value, audit uint32 }

func transformLeft(src *input) uint32 { return (src.left ^ 0x55) + 3 }
func readRight(src *input) uint32 { return src.right }
func goSelectValue(dst *output, src *input, selectValue uint32) {
	if selectValue != 0 { dst.value = transformLeft(src) } else { dst.value = readRight(src) }
}
func goMergeValues(dst *output, src *input, unused uint32) {
	left := transformLeft(src)
	dst.value = left + readRight(src)
}
func goFallbackValue(dst *output, src *input, unused uint32) { dst.value = 42 }

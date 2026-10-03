package main

type input struct{ left, right, noise uint32 }
type output struct {
	Balance uint32 `json:"balance"`
	Audit   uint32 `json:"-"`
}

func transformLeft(src *input) uint32 { return (src.left ^ 0x55) + 3 }
func readRight(src *input) uint32     { return src.right }
func goSelectValue(dst *output, src *input, choose uint32) {
	if choose != 0 {
		dst.Balance = transformLeft(src)
	} else {
		dst.Balance = readRight(src)
	}
}
func goMergeValues(dst *output, src *input, unused uint32) {
	left := transformLeft(src)
	dst.Balance = left + readRight(src)
}
func goFallbackValue(dst *output, src *input, unused uint32) { dst.Balance = 42 }
func goCopyLeft(dst *output, src *input, unused uint32)      { dst.Balance = src.left }

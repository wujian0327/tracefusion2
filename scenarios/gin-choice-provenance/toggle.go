package main

// The private selector evolves deterministically; every byte may have a
// different source even when both source arrays contain the same values.
func transform(dst, src, other *[4]byte, control *byte) {
 for i := 0; i < 4; i++ {
  if *control == 0 { dst[i] = src[i] } else { dst[i] = other[i] }
  *control ^= 1
 }
}

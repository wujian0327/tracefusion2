package main

// The control byte is not included in the configured work-entry snapshots.
// A single comparison site is executed once per output byte.
func transform(dst, src, other *[4]byte, control *byte) {
 for i := 0; i < 4; i++ {
  if *control == 0 { dst[i] = src[i] } else { dst[i] = other[i] }
 }
}

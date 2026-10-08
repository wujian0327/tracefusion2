package main

// Both tests read the same immutable request-private byte. The second loop is
// conditional: the first local choice is corrected, while the first remote
// choice survives. There is no unconditional final overwrite.
func transform(dst, src, other *[4]byte, control *byte) {
 for i := 0; i < 4; i++ {
  if *control == 0 { dst[i] = src[i] } else { dst[i] = other[i] }
 }
 if *control != 0 {
  for i := 0; i < 4; i++ { dst[i] = src[i] }
 }
}

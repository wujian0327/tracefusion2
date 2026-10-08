package main

// Negative control: changing only the second condition leaves the local choice
// uncorrected. Equal contents must not merge distinct source identities.
func transform(dst, src, other *[4]byte, control *byte) {
 for i := 0; i < 4; i++ {
  if *control == 0 { dst[i] = src[i] } else { dst[i] = other[i] }
 }
 if *control == 0 {
  for i := 0; i < 4; i++ { dst[i] = src[i] }
 }
}

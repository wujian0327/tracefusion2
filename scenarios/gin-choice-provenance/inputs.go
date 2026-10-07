package main

func transform(dst, src, other *[4]byte, control *[4]byte) {
 for i := 0; i < 4; i++ {
  if control[i] == 0 { dst[i] = src[i] } else { dst[i] = other[i] }
 }
}

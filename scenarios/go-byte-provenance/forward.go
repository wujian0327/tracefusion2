package main

func transform(dst, src *[4]byte) {
 for i := 0; i < len(dst); i++ {
  dst[i] = src[i] ^ 0x20
 }
}

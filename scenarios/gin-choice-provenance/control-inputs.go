package main

import "github.com/gin-gonic/gin"

// Four independent request inputs, immutable while transform executes.
// They arrive before the loop; this fixture does not perform I/O in the loop.
func readControl(c *gin.Context) *[4]byte {
 raw := c.Query("controls")
 if len(raw) != 4 { panic("controls must contain four binary digits") }
 value := new([4]byte)
 for i := 0; i < 4; i++ {
  if raw[i] != '0' && raw[i] != '1' { panic("invalid control digit") }
  value[i] = raw[i] - '0'
 }
 return value
}

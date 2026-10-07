package main

import "github.com/gin-gonic/gin"

func readControl(c *gin.Context) *byte {
 value := new(byte)
 if c.Query("pick") == "local" { *value = 1 }
 return value
}

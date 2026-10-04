package main

import (
 "net/http"
 "runtime"
 "github.com/gin-gonic/gin"
)

func run(c *gin.Context, aPath, bPath, cPath string, useC bool) {
 // Ordinary trace context extraction, not a provenance label or marker.
 parent := c.GetHeader("traceparent")
 a := readValue(aPath)
 b := readValue(bPath)
 other := readValue(cPath)
 selected := a
 if useC { selected = other }
 dst := new(output)
 transform(&dst.Result, selected, b)
 c.JSON(http.StatusOK, dst)
 runtime.KeepAlive(parent)
 runtime.KeepAlive(a)
 runtime.KeepAlive(b)
 runtime.KeepAlive(other)
 runtime.KeepAlive(dst)
}

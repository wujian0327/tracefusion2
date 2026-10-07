package main

import (
 "encoding/json"
 "context"
 "io"
 "net/http"
 "path/filepath"
 "runtime"
 "time"
 "github.com/gin-gonic/gin"
 "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

var remoteClient *http.Client

func setupClient() {
 remoteClient = &http.Client{Timeout:5*time.Second,Transport:otelhttp.NewTransport(http.DefaultTransport)}
}

func remoteURL(path string, useC bool) string {
 selected := "a"
 if useC { selected = "c" }
 ticket := filepath.Base(filepath.Dir(path))
 return "http://"+upstreamAddress+"/account/summary?ticket="+ticket+"&source="+selected
}

func readRemote(ctx context.Context, url string) *[4]byte {
 req,err := http.NewRequestWithContext(ctx,http.MethodGet,url,nil)
 if err!=nil { panic(err) }
 // otelhttp creates the CLIENT span and injects its context into headers.
 response,err := remoteClient.Do(req)
 if err!=nil { panic(err) }
 defer response.Body.Close()
 if response.StatusCode!=http.StatusOK { panic("upstream status") }
 body,err := io.ReadAll(response.Body)
 if err!=nil { panic(err) }
 decoded := new(output)
 if err=json.Unmarshal(body,decoded);err!=nil { panic(err) }
 return &decoded.Result
}

func readControl(c *gin.Context) *byte {
 value := new(byte)
 if c.Query("pick") == "local" { *value = 1 }
 return value
}

func run(c *gin.Context, aPath, bPath, cPath string, useC bool) {
 parent := c.GetHeader("traceparent")
 url := remoteURL(aPath,useC)
 a := readRemote(c.Request.Context(),url)
 b := readValue(bPath)
 other := readValue(cPath)
 control := readControl(c)
 dst := new(output)
 transform(&dst.Result,a,b,control)
 c.JSON(http.StatusOK,dst)
 runtime.KeepAlive(parent)
 runtime.KeepAlive(a)
 runtime.KeepAlive(b)
 runtime.KeepAlive(other)
 runtime.KeepAlive(dst)
}

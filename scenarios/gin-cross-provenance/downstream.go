package main

import (
 "encoding/json"
 "io"
 "net/http"
 "path/filepath"
 "runtime"
 "time"
 "github.com/gin-gonic/gin"
)

var remoteClient = &http.Client{Timeout: 5*time.Second}

func remoteURL(path string, useC bool) string {
 selected := "a"
 if useC { selected = "c" }
 ticket := filepath.Base(filepath.Dir(path))
 return "http://"+upstreamAddress+"/account/summary?ticket="+ticket+"&source="+selected
}

func readRemote(url, parent string) *[4]byte {
 req,err := http.NewRequest(http.MethodGet,url,nil)
 if err!=nil { panic(err) }
 // Forward the existing trace context. No lineage IDs are put on the wire.
 req.Header.Set("traceparent",parent)
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

func run(c *gin.Context, aPath, bPath, cPath string, useC bool) {
 parent := c.GetHeader("traceparent")
 url := remoteURL(aPath,useC)
 a := readRemote(url,parent)
 b := readValue(bPath)
 other := readValue(cPath)
 dst := new(output)
 transform(&dst.Result,a,b)
 c.JSON(http.StatusOK,dst)
 runtime.KeepAlive(a)
 runtime.KeepAlive(b)
 runtime.KeepAlive(other)
 runtime.KeepAlive(dst)
}

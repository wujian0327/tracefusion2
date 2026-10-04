package main

import (
 "context"
 "encoding/json"
 "net"
 "net/http"
 "os"
 "path/filepath"
 "runtime"
 "strconv"
 "strings"
 "sync"
 "time"
 "github.com/gin-gonic/gin"
)

const requestCount = 8
const concurrency = 4
var completed int
var observationMu sync.Mutex
var done = make(chan struct{})
var inputRoot string
var upstreamAddress string
type startup struct { Inputs, Upstream string }

type output struct { Result [4]byte `json:"result"` }

func readValue(path string) *[4]byte {
 b, err := os.ReadFile(path)
 if err != nil { panic(err) }
 if len(b) != 4 { panic("requires exactly four bytes") }
 value := new([4]byte)
 copy(value[:], b)
 return value
}


func handler(c *gin.Context) {
 ticket, err := strconv.Atoi(c.Query("ticket"))
 if err != nil || ticket < 1 || ticket > requestCount { c.AbortWithStatus(400); return }
 dir := filepath.Join(inputRoot, strconv.Itoa(ticket))
 run(c, filepath.Join(dir,"A.txt"), filepath.Join(dir,"B.txt"), filepath.Join(dir,"C.txt"), c.Query("source")=="c")
 observationMu.Lock()
 completed++
 if completed==requestCount { close(done) }
 observationMu.Unlock()
}

func schedulerInfo() map[string]any {
	_, maxSet := os.LookupEnv("GOMAXPROCS")
	flags := []string{}
	for _, item := range strings.Split(os.Getenv("GODEBUG"), ",") {
		name := strings.SplitN(item, "=", 2)[0]
		if name == "updatemaxprocs" || name == "containermaxprocs" || name == "asyncpreemptoff" {
			flags = append(flags, name)
		}
	}
	return map[string]any{"gomaxprocs": runtime.GOMAXPROCS(0), "num_cpu": runtime.NumCPU(),
		"gomaxprocs_env_set": maxSet, "scheduler_override_flags": flags}
}

func main() {
 // Collector attaches before stdin is released. No probe notification is added
 // to the business functions; this gate is only fixture startup control.
 var boot startup
 if err:=json.NewDecoder(os.Stdin).Decode(&boot); err!=nil { panic(err) }
 inputRoot=boot.Inputs; upstreamAddress=boot.Upstream
 gin.SetMode(gin.ReleaseMode)
 router:=gin.New()
 router.GET("/account/summary",handler)
 listener,err:=net.Listen("tcp4","127.0.0.1:0");if err!=nil { panic(err) }
 server:=&http.Server{Handler:router,ReadHeaderTimeout:5*time.Second}
 json.NewEncoder(os.Stdout).Encode(map[string]any{"address":listener.Addr().String(),"requests":requestCount,"concurrency":concurrency,"scheduler":schedulerInfo()})
 go func(){ if err:=server.Serve(listener);err!=nil && err!=http.ErrServerClosed { panic(err) } }()
 <-done
 ctx,cancel:=context.WithTimeout(context.Background(),5*time.Second);defer cancel()
 if err=server.Shutdown(ctx);err!=nil { panic(err) }
 json.NewEncoder(os.Stdout).Encode(map[string]any{"scheduler_final":schedulerInfo()})
}

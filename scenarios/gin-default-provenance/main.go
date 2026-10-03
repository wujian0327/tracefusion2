package main

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"

	"github.com/gin-gonic/gin"
)

const requestCount = 28
const concurrency = 4

var dataFiles [2]*os.File
var observationMu sync.Mutex // protects evaluation records only, outside scope
var done = make(chan struct{})
var observations []observation

type observation struct {
	Ticket    int    `json:"ticket"`
	Mode      string `json:"mode"`
	InputAddr uint64 `json:"input_addr"`
	KeepAlive *input `json:"-"` // avoid address reuse in evaluation identity mapping
}

func readField(fd int, dst *uint32, offset int64) {
	n, err := syscall.Pread(fd, unsafe.Slice((*byte)(unsafe.Pointer(dst)), 4), offset)
	runtime.KeepAlive(dst)
	if err != nil || n != 4 {
		panic("fixture pread failed")
	}
}

func serveAccount(c *gin.Context, mode string, src *input, ticket int) {
	off := int64((ticket - 1) * 16)
	if mode == "zero" {
		off += 8
	}
	if mode == "max" {
		off += 12
	}
	readField(int(dataFiles[0].Fd()), &src.left, off)
	readField(int(dataFiles[1].Fd()), &src.right, off)
	dst := new(output)
	switch mode {
	case "left":
		goSelectValue(dst, src, 1)
	case "right", "zero", "max":
		goSelectValue(dst, src, 0)
	case "merge":
		goMergeValues(dst, src, 0)
	case "overwrite":
		goSelectValue(dst, src, 1)
		goFallbackValue(dst, src, 0)
	case "same":
		goCopyLeft(dst, src, 0)
		goSelectValue(dst, src, 0)
	default:
		panic("unsupported fixture case")
	}
	c.JSON(http.StatusOK, dst)
	runtime.KeepAlive(dst)
}

func handler(c *gin.Context) {
	ticket, err := strconv.Atoi(c.Query("ticket"))
	mode := c.Query("mode")
	if err != nil || ticket < 1 || ticket > requestCount {
		c.AbortWithStatus(400)
		return
	}
	switch mode {
	case "left", "right", "merge", "overwrite", "same", "zero", "max":
	default:
		c.AbortWithStatus(400)
		return
	}
	src := &input{noise: 99} // request-private heap object; no shared input writer
	serveAccount(c, mode, src, ticket)
	// This record is evaluation-only. Inference never opens it or reads ticket.
	observationMu.Lock()
	observations = append(observations, observation{Ticket: ticket, Mode: mode, InputAddr: uint64(uintptr(unsafe.Pointer(src))), KeepAlive: src})
	if len(observations) == requestCount {
		close(done)
	}
	observationMu.Unlock()
}

func prepare() func() {
	dir, err := os.MkdirTemp(".", "tracefusion-gin-default-")
	if err != nil {
		panic(err)
	}
	data := make([]byte, requestCount*16)
	for ticket := 0; ticket < requestCount; ticket++ {
		for i, v := range []uint32{424242, 424243, 0, 0xffffffff} {
			binary.LittleEndian.PutUint32(data[ticket*16+i*4:], v)
		}
	}
	for i, name := range []string{"a.bin", "b.bin"} {
		path := filepath.Join(dir, name)
		if err = os.WriteFile(path, data, 0600); err != nil {
			panic(err)
		}
		dataFiles[i], err = os.Open(path)
		if err != nil {
			panic(err)
		}
	}
	return func() {
		for _, f := range dataFiles {
			f.Close()
		}
		os.RemoveAll(dir)
	}
}

// Read-only runtime metadata for evaluation. Do not set GOMAXPROCS, yield,
// delay, pin, or coordinate phases in any request handler.
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
	cleanup := prepare()
	defer cleanup()
	gin.SetMode(gin.ReleaseMode)
	router := gin.New()
	router.GET("/account/summary", handler)
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		panic(err)
	}
	server := &http.Server{Handler: router, ReadHeaderTimeout: 5 * time.Second}
	if err = json.NewEncoder(os.Stdout).Encode(map[string]any{"address": listener.Addr().String(), "requests": requestCount, "concurrency": concurrency, "scheduler": schedulerInfo()}); err != nil {
		panic(err)
	}
	if len(os.Args) == 2 && os.Args[1] == "--wait" {
		if err = syscall.Kill(os.Getpid(), syscall.SIGSTOP); err != nil {
			panic(err)
		}
	}
	go func() {
		if err := server.Serve(listener); err != nil && err != http.ErrServerClosed {
			panic(err)
		}
	}()
	<-done
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err = server.Shutdown(ctx); err != nil {
		panic(err)
	}
	if err = json.NewEncoder(os.Stderr).Encode(observations); err != nil {
		panic(err)
	}
	if err = json.NewEncoder(os.Stdout).Encode(map[string]any{"scheduler_final": schedulerInfo()}); err != nil {
		panic(err)
	}
	runtime.KeepAlive(dataFiles)
	runtime.KeepAlive(observations)
}

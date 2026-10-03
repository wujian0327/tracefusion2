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
	"sync"
	"syscall"
	"time"
	"unsafe"

	"github.com/gin-gonic/gin"
)

// Serial fixture only. pread is the sole writer of input fields in each scope.
var sourceBuffer = input{noise: 99}
var dataFiles [2]*os.File
var observations []map[string]any // evaluation-only, never read by inference
var serial sync.Mutex
var done = make(chan struct{})
var handled int

const requestCount = 14

func readField(fd int, dst *uint32, offset int64) {
	n, err := syscall.Pread(fd, unsafe.Slice((*byte)(unsafe.Pointer(dst)), 4), offset)
	runtime.KeepAlive(dst)
	if err != nil || n != 4 {
		panic("fixture pread failed")
	}
}

// Ordinary business code and normal Gin JSON response; no custom serializer,
// response-writer wrapper, taint tags or per-field tracing calls.
func serveAccount(c *gin.Context, mode string) {
	off := int64(0)
	if mode == "zero" {
		off = 8
	}
	if mode == "max" {
		off = 12
	}
	readField(int(dataFiles[0].Fd()), &sourceBuffer.left, off)
	readField(int(dataFiles[1].Fd()), &sourceBuffer.right, off)
	dst := new(output)
	switch mode {
	case "left":
		goSelectValue(dst, &sourceBuffer, 1)
	case "right", "zero", "max":
		goSelectValue(dst, &sourceBuffer, 0)
	case "merge":
		goMergeValues(dst, &sourceBuffer, 0)
	case "overwrite":
		goSelectValue(dst, &sourceBuffer, 1)
		goFallbackValue(dst, &sourceBuffer, 0)
	case "same":
		goCopyLeft(dst, &sourceBuffer, 0)
		goSelectValue(dst, &sourceBuffer, 0)
	default:
		panic("unsupported fixture case")
	}
	c.JSON(http.StatusOK, dst)
	runtime.KeepAlive(dst)
}

func handler(c *gin.Context) {
	// This first framework experiment deliberately excludes parallel requests
	// and OS-thread migration inside a scope; check actual G on every boundary.
	serial.Lock()
	defer serial.Unlock()
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	mode := c.Query("mode")
	switch mode {
	case "left", "right", "merge", "overwrite", "same", "zero", "max":
	default:
		c.AbortWithStatus(http.StatusBadRequest)
		return
	}
	serveAccount(c, mode)
	observations = append(observations, map[string]any{"mode": mode})
	handled++
	if handled == requestCount {
		close(done)
	}
}

func prepare() func() {
	dir, err := os.MkdirTemp(".", "tracefusion-gin-")
	if err != nil {
		panic(err)
	}
	data := make([]byte, 16)
	for i, v := range []uint32{424242, 424243, 0, 0xffffffff} {
		binary.LittleEndian.PutUint32(data[i*4:], v)
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
	// Readiness is outside the observed request scopes. Traffic is driven by
	// the Python client after all probes have been attached.
	if err = json.NewEncoder(os.Stdout).Encode(map[string]any{"address": listener.Addr().String(), "requests": requestCount}); err != nil {
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
	// Only evaluation opens this record; it is not a source of inferred edges.
	if err = json.NewEncoder(os.Stderr).Encode(observations); err != nil {
		panic(err)
	}
	runtime.KeepAlive(dataFiles)
}

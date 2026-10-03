package main

import (
	"encoding/binary"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"syscall"
	"unsafe"
)

// Fixed storage avoids treating a moving goroutine stack as a stable I/O
// buffer. This fixture does not claim general heap/stack lifetime tracking.
var inputBuffer = input{noise: 99}
var answers [18]caseResult

type readSource struct {
	ID uint32 `json:"io_id"`
	Name string `json:"file_name"`
	Offset uint32 `json:"file_offset"`
	Length uint32 `json:"length"`
}
type caseResult struct {
	Sequence uint32 `json:"sequence"`
	Case uint32 `json:"case"`
	Round uint32 `json:"round"`
	Function string `json:"function"`
	Sources []string `json:"expected_sources"`
	Expected uint32 `json:"expected_value"`
	Output uint32 `json:"output"`
	Attempts uint32 `json:"expected_read_attempts"`
	External []readSource `json:"expected_external_sources"`
}

func readChecked(fd int, dst *uint32, offset int64, expected int) {
	// A byte view only; no copy/decoder, source tag or custom instrumentation.
	buf := unsafe.Slice((*byte)(unsafe.Pointer(dst)), 4)
	n, err := syscall.Pread(fd, buf, offset)
	runtime.KeepAlive(dst)
	if expected < 0 {
		if err != syscall.EBADF || n != -1 { panic("expected EBADF") }
	} else if err != nil || n != expected { panic("unexpected pread result") }
}

func runWorkload(a, b int) {
	var sequence, reads uint32
	for round := uint32(0); round < 2; round++ {
		off := round*4
		v := uint32(424242)+round
		for c := uint32(0); c < 9; c++ {
			dst := output{0xdeadbeef, 0}
			first := reads+1
			expectedID, sourceOffset := first, off
			file, name := "a.bin", "main.goSelectValue"
			fields := []string{"input.left"}
			sourceCount := 1
			expected := (v^0x55)+3
			if c <= 2 {
				readChecked(a, &inputBuffer.left, int64(off), 4)
				readChecked(b, &inputBuffer.right, int64(off), 4)
				reads += 2
				switch c {
				case 0: goSelectValue(&dst, &inputBuffer, 1)
				case 1:
					goSelectValue(&dst, &inputBuffer, 0)
					expected, expectedID, file = v, first+1, "b.bin"
					fields = []string{"input.right"}
				case 2:
					goMergeValues(&dst, &inputBuffer, 0)
					expected += v
					name, sourceCount = "main.goMergeValues", 2
					fields = []string{"input.left", "input.right"}
				}
			} else if c == 7 {
				readChecked(-1, &inputBuffer.left, int64(off), -1)
				reads++
				goFallbackValue(&dst, &inputBuffer, 0)
				expected, name, sourceCount = 42, "main.goFallbackValue", 0
				fields = []string{}
			} else {
				readChecked(a, &inputBuffer.left, int64(off), 4)
				reads++
				switch c {
				case 3:
					readChecked(b, &inputBuffer.left, int64(off), 4)
					expectedID, file = first+1, "b.bin"
				case 4:
					readChecked(a, &inputBuffer.left, int64((1-round)*4), 4)
					expectedID, sourceOffset = first+1, (1-round)*4
					expected = ((424243-round)^0x55)+3
				case 5: readChecked(-1, &inputBuffer.left, int64(off), -1)
				case 6: readChecked(b, &inputBuffer.left, 8, 0)
				case 8:
					readChecked(a, &inputBuffer.left, int64(off), 4)
					expectedID = first+1
				}
				reads++
				goSelectValue(&dst, &inputBuffer, 1)
			}
			// Independent harness oracle, consumed only after inference.
			external := []readSource{}
			if sourceCount > 0 { external = append(external, readSource{expectedID,file,sourceOffset,4}) }
			if sourceCount == 2 { external = append(external, readSource{first+1,"b.bin",off,4}) }
			answers[sequence] = caseResult{sequence+1,c,round,name,fields,expected,dst.value,reads,external}
			sequence++
		}
	}
}

func main() {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	dir, err := os.MkdirTemp(".", "tracefusion-go-read-")
	if err != nil { panic(err) }
	defer os.RemoveAll(dir)
	var files [2]*os.File
	data := make([]byte, 8)
	binary.LittleEndian.PutUint32(data,424242)
	binary.LittleEndian.PutUint32(data[4:],424243)
	for i, name := range []string{"a.bin", "b.bin"} {
		path := filepath.Join(dir,name)
		if err := os.WriteFile(path,data,0600); err != nil { panic(err) }
		files[i], err = os.Open(path)
		if err != nil { panic(err) }
		defer files[i].Close()
	}
	a,b := int(files[0].Fd()),int(files[1].Fd())
	if len(os.Args)==2 && os.Args[1]=="--wait" {
		if err := syscall.Kill(os.Getpid(),syscall.SIGSTOP); err != nil { panic(err) }
	}
	runtime.Gosched()
	runWorkload(a,b)
	runtime.KeepAlive(files)
	encoder := json.NewEncoder(os.Stdout)
	for _, answer := range answers { if err := encoder.Encode(answer); err != nil { panic(err) } }
}

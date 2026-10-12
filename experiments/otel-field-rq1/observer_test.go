// Validation-only observer. It does not compute or propagate provenance tags.
package main

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"sync"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc/stats"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
)

type rq1Log struct {
	mu       sync.Mutex
	f        *os.File
	seq      int
	retained []any
	role     string
}

func rq1Open(role string) (*rq1Log, *sdktrace.TracerProvider, error) {
	f, err := os.OpenFile(os.Getenv("RQ1_LOG"), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if err != nil {
		return nil, nil, err
	}
	log := &rq1Log{f: f, role: role}
	provider := sdktrace.NewTracerProvider(sdktrace.WithSampler(sdktrace.AlwaysSample()), sdktrace.WithSyncer(log))
	otel.SetTracerProvider(provider)
	otel.SetTextMapPropagator(propagation.TraceContext{})
	return log, provider, nil
}
func rq1Context(ctx context.Context) map[string]any {
	s := trace.SpanContextFromContext(ctx)
	return map[string]any{"trace_id": s.TraceID().String(), "span_id": s.SpanID().String(), "valid": s.IsValid()}
}
func (l *rq1Log) write(row map[string]any) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.seq++
	row["sequence"] = l.seq
	row["role"] = l.role
	row["pid"] = os.Getpid()
	if err := json.NewEncoder(l.f).Encode(row); err != nil {
		panic(err)
	}
}
func (l *rq1Log) retain(v any) { l.mu.Lock(); defer l.mu.Unlock(); l.retained = append(l.retained, v) }
func rq1Pointer(v any) string  { return fmt.Sprintf("0x%x", reflect.ValueOf(v).Pointer()) }
func (l *rq1Log) message(v any) map[string]any {
	m, ok := v.(proto.Message)
	if !ok {
		panic("non-protobuf payload")
	}
	l.retain(v) // Prevent pointer reuse within this validation process.
	b, err := proto.MarshalOptions{Deterministic: true}.Marshal(m)
	if err != nil {
		panic(err)
	}
	j, err := protojson.MarshalOptions{UseProtoNames: true, EmitUnpopulated: true}.Marshal(m)
	if err != nil {
		panic(err)
	}
	d := m.ProtoReflect().Descriptor()
	numbers := map[string]int{}
	for i := 0; i < d.Fields().Len(); i++ {
		f := d.Fields().Get(i)
		numbers[string(f.Name())] = int(f.Number())
	}
	return map[string]any{"type": string(d.FullName()), "pointer": rq1Pointer(v), "fields": json.RawMessage(j),
		"field_numbers": numbers, "snapshot_hex": hex.EncodeToString(b),
		"snapshot_semantics": "deterministic reserialization of observed typed payload; NOT raw wire capture"}
}
func (l *rq1Log) ExportSpans(_ context.Context, spans []sdktrace.ReadOnlySpan) error {
	for _, s := range spans {
		c, p := s.SpanContext(), s.Parent()
		l.write(map[string]any{"kind": "span", "trace_id": c.TraceID().String(), "span_id": c.SpanID().String(),
			"parent_trace_id": p.TraceID().String(), "parent_span_id": p.SpanID().String(), "parent_remote": p.IsRemote(),
			"span_kind": int(s.SpanKind()), "name": s.Name(), "scope": s.InstrumentationScope(),
			"start": s.StartTime().Format(time.RFC3339Nano), "end": s.EndTime().Format(time.RFC3339Nano)})
	}
	return nil
}
func (l *rq1Log) Shutdown(context.Context) error { return nil }

type rq1MethodKey struct{}
type rq1Stats struct {
	base stats.Handler
	log  *rq1Log
}

func (s *rq1Stats) TagRPC(ctx context.Context, i *stats.RPCTagInfo) context.Context {
	return context.WithValue(s.base.TagRPC(ctx, i), rq1MethodKey{}, i.FullMethodName)
}
func (s *rq1Stats) HandleRPC(ctx context.Context, event stats.RPCStats) {
	var v any
	var length, wire int
	var direction string
	switch e := event.(type) {
	case *stats.InPayload:
		v = e.Payload
		length = e.Length
		wire = e.WireLength
		direction = "in"
	case *stats.OutPayload:
		v = e.Payload
		length = e.Length
		wire = e.WireLength
		direction = "out"
	}
	if v != nil {
		s.log.write(map[string]any{"kind": "payload", "direction": direction, "method": ctx.Value(rq1MethodKey{}),
			"context": rq1Context(ctx), "message": s.log.message(v), "payload_bytes": length, "grpc_frame_bytes": wire})
	}
	s.base.HandleRPC(ctx, event)
}
func (s *rq1Stats) TagConn(ctx context.Context, i *stats.ConnTagInfo) context.Context {
	return s.base.TagConn(ctx, i)
}
func (s *rq1Stats) HandleConn(ctx context.Context, i stats.ConnStats) { s.base.HandleConn(ctx, i) }

package main

import (
 "context"
 "encoding/json"
 "fmt"
 "io"
 "net/http"
 "os"
 "sort"
 "sync"
 "time"
 "go.opentelemetry.io/otel"
 "go.opentelemetry.io/otel/attribute"
 "go.opentelemetry.io/otel/propagation"
 "go.opentelemetry.io/otel/codes"
 "go.opentelemetry.io/otel/trace"
)

type clientBoot struct { Address, TraceFile, Responses string }
type responseRecord struct {
 Ticket int `json:"ticket"`
 Selected string `json:"selected"`
 Trace string `json:"trace"`
 Status int `json:"status"`
 ContentType string `json:"content_type"`
 Body string `json:"body"`
 ElapsedNS int64 `json:"elapsed_ns"`
}

func main() {
 var boot clientBoot
 if err:=json.NewDecoder(os.Stdin).Decode(&boot);err!=nil { panic(err) }
 shutdown:=initTracing("driver",boot.TraceFile);defer shutdown()
 tracer:=otel.Tracer("tracefusion.load-client")
 ctx,root:=tracer.Start(context.Background(),"load-test")
 var wg sync.WaitGroup
 var mu sync.Mutex
 rows:=make([]responseRecord,0,8)
 for worker:=1;worker<=4;worker++ {
  wg.Add(1)
  go func(index int) {
   defer wg.Done()
   client:=&http.Client{Timeout:15*time.Second}
   for _,ticket:=range []int{index,index+4} {
    selected:="a";if ticket%2==0 { selected="c" }
    url:=fmt.Sprintf("http://%s/account/summary?ticket=%d&source=%s",boot.Address,ticket,selected)
    requestCtx,span:=tracer.Start(ctx,"GET /account/summary",trace.WithSpanKind(trace.SpanKindClient),
     trace.WithAttributes(attribute.String("http.request.method","GET"),attribute.String("url.full",url)))
    if ticket%4 >= 2 { url += "&pick=local" } else { url += "&pick=remote" }
    // Only the indexed-input scenario consumes this query. Equal first/last
    // digits with different middle digits defeat reusing a single seed.
    controls := [...]string{"0000","0100","0010","0110","1001","1101","1011","1111"}
    url += "&controls=" + controls[ticket-1]
    req,err:=http.NewRequestWithContext(requestCtx,http.MethodGet,url,nil);if err!=nil { panic(err) }
    // SDK-owned IDs and standard propagation; no custom trace generator.
    otel.GetTextMapPropagator().Inject(requestCtx,propagation.HeaderCarrier(req.Header))
    started:=time.Now()
    response,err:=client.Do(req);if err!=nil { span.RecordError(err);span.SetStatus(codes.Error,err.Error());span.End();panic(err) }
    body,err:=io.ReadAll(response.Body);response.Body.Close();if err!=nil { panic(err) }
    elapsed:=time.Since(started).Nanoseconds()
    span.SetAttributes(attribute.Int("http.response.status_code",response.StatusCode));span.End()
    row:=responseRecord{ticket,selected,req.Header.Get("traceparent"),response.StatusCode,response.Header.Get("Content-Type"),string(body),elapsed}
    mu.Lock();rows=append(rows,row);mu.Unlock()
   }
  }(worker)
 }
 wg.Wait();root.End()
 sort.Slice(rows,func(i,j int)bool{return rows[i].Ticket<rows[j].Ticket})
 file,err:=os.Create(boot.Responses);if err!=nil { panic(err) }
 if err=json.NewEncoder(file).Encode(rows);err!=nil { panic(err) };file.Close()
}

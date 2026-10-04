package main

import (
 "context"
 "os"
 "time"
 "go.opentelemetry.io/otel"
 "go.opentelemetry.io/otel/attribute"
 "go.opentelemetry.io/otel/exporters/stdout/stdouttrace"
 "go.opentelemetry.io/otel/propagation"
 "go.opentelemetry.io/otel/sdk/resource"
 sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func initTracing(service,path string) func() {
 file,err:=os.Create(path)
 if err!=nil { panic(err) }
 exporter,err:=stdouttrace.New(stdouttrace.WithWriter(file))
 if err!=nil { file.Close();panic(err) }
 provider:=sdktrace.NewTracerProvider(
  sdktrace.WithSampler(sdktrace.AlwaysSample()),
  sdktrace.WithResource(resource.NewWithAttributes("",attribute.String("service.name",service))),
  sdktrace.WithBatcher(exporter),
 )
 otel.SetTracerProvider(provider)
 otel.SetTextMapPropagator(propagation.TraceContext{})
 return func() {
  ctx,cancel:=context.WithTimeout(context.Background(),5*time.Second);defer cancel()
  if err:=provider.Shutdown(ctx);err!=nil { file.Close();panic(err) }
  if err:=file.Close();err!=nil { panic(err) }
 }
}

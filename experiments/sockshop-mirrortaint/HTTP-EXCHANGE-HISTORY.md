# Explicit HTTP exchange proof and intermediate history inputs

This optional protocol does not reinterpret old captures. `http_exchange.version=1`
admits a frozen, blocking HTTP/1.1 adapter, flat default-schema scalar DTOs and one
exchange per fresh TCP connection. Actual completed Socket and HttpExchange I/O
records precede their codec snapshots. Evidence includes local carrier identity,
oriented client/server endpoints, actual wire traceparent, operation, direction,
raw body, hash, status, adapter/server implementation hashes and capture/process
namespace. The JVM source and compiled adapter are both retained in receipts.

Remote edges require matching real endpoints, concrete wire invocation,
operation, direction and exact schema-derived JSON property. Byte/value checks
validate an already selected edge. Object numbers are never compared across
processes. Missing/ambiguous message evidence cannot be repaired by equal values,
trace alone, timing, workload names or expected sources. Swapped equal-valued
property paths fail against the frozen default JSON schema. Keepalive, proxies,
retries, TLS, multiplexing, arbitrary codecs and nested DTOs are not admitted.

Session history v1 retains direct external HTTP input semantics and still
rejects outbound RPC. v2 admits only an explicitly declared `intermediate` HTTP
input, validated under this protocol, with sequential application roots. Its
local `http` origins are dependency endpoints, not external sources. The final
distributed graph must connect them through communication proof to an
`external` request boundary; a query cannot promote B's intermediate input to
an external source. Unbound endpoints remain unknown. Actual writes, exact
versions, immutable history, opaque effect barriers and request-local State
remain as in v1. B does not execute outbound RPC in this scope. A uses the
transport-boundary plan; its actual forwarding uses same-process field identity
and counted version, never equality-based inference.

Raw capture and offline inference source receipts are separate. Offline
improvements do not modify old events or synthesize missing initialization or
write evidence. In particular, unobserved Cache.cell@0 still produces unknown;
the initial-state calibration is preserved rather than granted a default fact.

MirrorTaint paper-style composition is a separate experiment implementation. It
uses only public native local input/output IDs plus actual message coordinates,
not TF's execution graph, field history or answers. Its local interface tokens
are not transported external labels. This reproduction is explicitly distinct
from the unavailable author post-analysis entry and from raw online tags.

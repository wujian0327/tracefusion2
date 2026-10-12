# External Galette comparison: original byte-array hash path

This experiment uses **upstream Galette**, not a reimplementation of its algorithm.
Pinned repository: <https://github.com/neu-se/galette>, commit
`bc6002cc5ee4d6eaa30518b2d176a9831d77cb1a`.
Paper: Katherine Hough and Jonathan Bell, *Dynamic Taint Tracking for Modern Java
Virtual Machines*, FSE 2025, <https://doi.org/10.1145/3729349>.

## Scope and interpretation

The application is the unchanged Commons Codec 1.17.1 release JAR and the original
`MurmurHash2.hash32(byte[], int, int)` / `getLittleEndianInt` call path. Inputs and
independent oracle are exactly the existing 20 array cases from `compare_arrays.py`.
No new business functions, vulnerabilities, or favorable-only inputs are introduced.

For Galette the adapter assigns distinct `Tag.of("rN.byteI")` tags through
`Tainter.setTag` to **every** array element, including unread suffix elements. It
also labels the length parameter and seed, then queries `Tainter.getTag` on the
actual return value. It does not install an expected return tag or read our query
planner, traces, graph, or oracle. Dedicated default-JVM and `-Xint` runs archive
the value and actual tag of every labeled input, as well as every return tag.

The truth is operational operand provenance, not minimal bit/counterfactual
influence. Galette's unmodified `ArrayTagStore` propagates index tags; our graph
keeps addresses separate. On this path indices can introduce the already present
length label, which also participates directly in `seed ^ length`. Thus the
expected source sets coincide **on these inputs**; the general semantics differ.

Five groups share the same driver, inputs, release JAR and base JDK version:
native, our full/sparse/boundary modes, and Galette. Galette runs on its required
instrumented copy of that same JDK. Our groups instrument only the declared
method closure; upstream Galette instruments the JCL and application more broadly.
This is a **deployment cost comparison for a specified query**, not an equal-scope
microbenchmark proving one propagation algorithm intrinsically faster. Galette
can analyze behavior outside our supported subset. No performance result here
establishes general superiority or whole-application coverage.

All five groups use **standard JVM default verification**, as in upstream's run
instructions; none uses `-noverify` or `-Xverify:none`. On our Corretto 17.0.20.1
installation, the unmodified instrumented JDK fails the additional `-Xverify:all`
startup probe with `VerifyError` in `AbstractStringBuilder.append(int)` (receiver
type versus `StringBuilder`). Default startup succeeds. Both probe outputs are
archived in every run. This limitation is not hidden and default-startup success
does not establish that all transformed JCL bytecode passes strict verification.
The older three-mode experiment used `-Xverify:all`; do not merge those costs.

## Run

Requires Linux, a complete **JDK 17**, Maven 3.6+, Python 3, a C compiler, git,
and dependency-download access. `JDK17` below must be the actual JDK installation
root, containing `bin/java` and `bin/javac`. The preparation script validates the
version instead of silently accepting the default JDK 21.

```bash
git switch perf/payment-steady-state
git pull --ff-only
"$JDK17/bin/java" -version
python experiments/java-collection/prepare_galette.py \
  --jdk "$JDK17" --output artifacts/galette-jdk17
python experiments/java-collection/compare_galette.py \
  --jdk "$JDK17" --galette artifacts/galette-jdk17 \
  --rounds 2 --jvm-warmup 0 --repeats 6 --warmup 1
```

Preparation clones the pinned upstream revision, checks for tracked changes,
builds the upstream agent and instrumenter, and creates a **new** JDK directory.
It never changes the original JDK. Build and JDK instrumentation costs are recorded
separately. An existing clean checkout can be supplied using `--source`; reuse of
its built JARs using `--skip-build` is explicitly recorded and requires retaining
the original build logs separately.

The runner prints an `artifacts/java-galette-...` directory. Re-read that archive:

```bash
python experiments/java-collection/verify_galette.py \
  artifacts/java-galette-ACTUAL-RUN-DIRECTORY \
  --output artifacts/java-galette-verification.json
```

Use the exact directory printed by the runner; `ACTUAL-RUN-DIRECTORY` is not a
literal path. Archive it together with the verification JSON and the preparation
JSON/logs. The JDK itself need not be uploaded; its `release`, launcher, and
`lib/modules` hashes are recorded and checked before execution.

## Costs and qualification

* Randomized, recorded five-group block order; six measured blocks by default.
  Separate-process preparation blocks do not warm a later JVM's JIT.
* Online whole-command wall/CPU includes JVM startup, loading/transformation,
  input construction, source binding or snapshots, analysis/collection, and output.
  The parent reads stdout/stderr through pipes and saves the actual received bytes;
  wall time includes that persistence. Child CPU comes from the C supervisor's
  `wait4`, so parent Python persistence CPU is excluded for all groups.
* Our offline wall/CPU includes Python startup, decoding, graph construction and
  query results. Galette performs propagation and return-tag extraction online;
  there is no separately timed offline inference stage for it.
* End-to-end wall/CPU is the sum of online and offline stages. The script reports
  paired reductions relative to Galette; negative values mean our group is slower.
* RSS is retained as raw diagnostics, **not a qualified memory advantage**. Event
  counts only describe our collectors; Galette tags are not comparable trace events.
* A `WINDOW` record measures an application-internal interval. `--jvm-warmup N`
  runs N rounds in that same JVM before the interval. Warmup captures are retained
  and their inference remains part of the whole-command cost. The interval includes
  input setup, tag operations and result buffering, but not final stdout flushing.
  It excludes startup and is **diagnostic only**, not proof of JIT convergence or
  steady-state performance. Process CPU resolution can be coarse on small loads.

For an additional warmed-window diagnostic, use a separate run with
`--rounds 5 --jvm-warmup 5`. Do not combine its medians with the cold-run table or
the earlier JDK 21 host results. A longer calibrated steady-state protocol remains
separate work; these bounded short workloads alone cannot establish it.
Pass `--reuse-correctness` with a previous intact run directory to reuse the two
external correctness captures when adapter, Galette agent, base JDK and instrumented
JDK match. Every new cost invocation is still checked for individual values/sources.

`verify_galette.py` rechecks artifact hashes, input tags, all individual return
values and sources, each raw trace, snapshot-to-input binding, three-mode answer
equality, resource records, randomized order, and paired summaries. A runner status
of `collected` by itself is not a verified publication result.

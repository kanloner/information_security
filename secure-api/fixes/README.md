# Fix for CVE-2021-25646

The vulnerability is fixed by upgrading Apache Druid to 0.20.1, which rejects
the empty-key (`""`) override that re-enabled the JavaScript parsing feature.

## What changed

```diff
 services:
   druid:
-    image: vulhub/apache-druid:0.20.0
+    build:
+      context: .
+      dockerfile: Dockerfile     # builds a 0.20.1 image (see below)
```

`0.20.1` is the official release that fixes CVE-2021-25646. The root cause was
a missing validation in the Jackson deserializer: a crafted JSON body containing
an empty key (`""`) was able to override the `enabled` flag of the JavaScript
parser, so the feature ran even when it was configured off. In 0.20.1 the
override is rejected, so the `function` field of a sampler request is never
passed to the Rhino engine, and `java.lang.Runtime.getRuntime().exec()` can no
longer be reached.

## Why a Dockerfile instead of a plain image tag

The official `apache/druid:0.20.1` image is built on a **distroless** base that
cannot run the `start-nano-quickstart` launcher (it has neither `bash` nor
`perl`, which the launcher scripts require). To keep the vulnerable and fixed
environments comparable - same launcher, same embedded ZooKeeper, same ports -
`fixes/Dockerfile` keeps the vulhub 0.20.0 base (which provides those tools) and
replaces only the vulnerable `0.20.0` jars with the fixed `0.20.1` jars copied
from the official image. The result is a 0.20.1 server that starts identically
to the vulnerable one.

## Apply and verify

```bash
docker compose -f cve/CVE-2021-25646/docker-compose.yml down
docker compose -f fixes/docker-compose.yml up -d --build
./cve/CVE-2021-25646/verify_fix.sh
```

Expected on the fixed version: the same sampler request returns
`{"error":"Failed to sample data: JavaScript is disabled"}` and no command
output, while the Druid console still answers on `:8888`.

## Alternative mitigations (not used here)

If upgrading were impossible, the vulnerability can be mitigated by restricting
network access to the Druid console to trusted hosts, or by ensuring the
JavaScript parsing feature stays disabled and rejecting any sampler request
whose `parseSpec.format` is `javascript` at a reverse proxy in front of Druid.
Neither is as complete as the patch, because the empty-key override would still
bypass a purely configuration-based guard on vulnerable versions.

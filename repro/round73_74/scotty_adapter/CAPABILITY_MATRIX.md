# Capability matrix (contract-level, not an accuracy ranking)

| Capability | Scotty 0.4 | MT-Memory tiered service | Comparison status |
|---|---:|---:|---|
| Tumbling windows | Yes | Can issue equivalent interval queries | Direct common subset |
| Sliding windows | Yes | Can issue equivalent interval queries | Direct common subset |
| Session windows | Yes | No formal session operator | Scotty-only |
| Out-of-order events within lateness | Yes | Current service uses ordered ingestion | Scotty-only |
| Shared partial aggregates across registered windows | Yes | Coarse buckets plus selected overlays | Related but distinct |
| Arbitrary delayed interval query not registered in advance | No general query API | Yes within declared reach | MT-Memory-only |
| Guaranteed coarse answer across declared reach | Only registered windows/lateness | Yes | MT-Memory-only contract |
| Exact latest fact lookup and overwrite | No | Yes, bounded cache/catalog | MT-Memory-only |
| Selective fact deletion/tombstone | No | Yes | MT-Memory-only |
| Workload-driven replacement of fine history | No published controller API | Yes | MT-Memory-only |
| Built-in checkpoint/state-backend support in this release | Roadmap item | Two-slot external layer tested | Not direct |

Scotty capabilities are based on the frozen official README and the inspected
0.4 source at commit `b89b7fc2e2b0813ba0f56834c8f9bc9bfceee189`.

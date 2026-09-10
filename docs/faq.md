# FAQ

**Is this one GPU doing tensor parallelism across three cards?**
No. Three independent ComfyUI workers, one per GPU, pulling shards from a
queue. Parallelism is at the batch level, not the tensor level.

**Why is model loading excluded from the benchmark?**
Because it's a one-time cost amortized over the worker's lifetime. Workers
are long-lived; weights are loaded once and stay resident. Timing a
steady-state pipeline including cold start would measure your disk, not
your pipeline.

**Does it work on one GPU?**
Yes. The orchestrator serializes shards. Same workflow, same receipt
contract — wall clock scales roughly linearly with shard count.

**What about 24 GB cards (4090-class)?**
Not for this profile. MiniMax-H3 at 608×352/226f/4-step plus the audio
stack wants 32 GB. Lower frame counts or resolutions may fit; tune the
workflow and re-benchmark.

**Why 4 steps?**
It's the quality/speed point we chose for this workload. More steps are
a workflow-parameter change, not a deployment change — expect RTF to scale
roughly with step count.

**Do workers need fast interconnect?**
No. Workers never communicate with each other. The only network traffic is
orchestrator→worker prompt submission and worker→orchestrator receipts and
output files. Plain LAN is fine.

**Can workers be on different machines?**
Yes — a worker is just a URL. One 3-GPU box and three 1-GPU boxes behave
identically.

**What happens if a worker dies mid-job?**
Its shard times out and is re-queued to a healthy worker. The job gets
slower, not failed. See `docs/architecture.md`.

**Is MiniMax-H3 included in this repo?**
No. Weights are downloaded by `deploy/setup_worker.sh` from the upstream
source at install time. Check the model's license before use.

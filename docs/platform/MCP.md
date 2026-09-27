# Runtime MCP Control

Freebuff includes a local stdio MCP server for inspecting runtime state and
tuning candidate-review policy without editing ENV or restarting the worker.

Run it from the repository:

```bash
./.venv/bin/freebuff-mcp
```

The server exposes:

- `read_runtime_settings` — PAPER/DEMO/LIVE state and candidate policy
- `read_runtime_status` — worker heartbeat and latest decision
- `read_candidate_summary` — observe/batch/immediate counts
- `update_candidate_policy` — change thresholds and AI review budget
- `set_trading_mode` — change PAPER/DEMO; LIVE requires `ENABLE LIVE TRADING`

The MCP surface cannot place orders, edit credentials, or change Risk Engine
limits. It is intentionally stdio-only and should be registered with the local
MCP client. To control a production instance, run the MCP process in the same
container/volume as the worker so it can access `/app/data`; a local process
cannot see Coolify's private volume automatically.

Candidate review policy is persisted in `/app/data/runtime_control.json`:

```json
{
  "observe_min_score": 0,
  "batch_min_score": 55,
  "immediate_min_score": 70,
  "max_immediate_per_bar": 3,
  "summary_window": 25
}
```

All candidates above the observation floor are recorded by the local triage
layer. Only immediate candidates can reach the AI Council in real time; batch
and observe candidates contribute to the compact digest and remain available
for later outcome analysis.

# AI audit fixes — 2026-09-10

## Implemented

- Strict, versioned JSON contracts for GPT/Gemini; malformed, contradictory,
  duplicate-key, out-of-range and substring-only responses reject with zero confidence.
- Main app constructs Council, learner and EQH/EQL detector; actual H1/M15
  structures reach provider prompts. The final forming bar is excluded from
  strategy context, and the previous bar is refreshed when a new bar opens.
- Broker execution through OrderManager requires explicit DEMO. PAPER does not
  send broker orders; LIVE remains disabled. The existing separate paper simulator
  is not represented as a broker fill by this orchestrator.
- Both gateways implement get_position_deals(position_id). Bridge server changes
  live in the separate mt5-bridge repository. Snapshot/history errors are not empty
  position lists. The tracker retries incomplete history rather than learning from
  the last floating PnL.
- New additive learning_evidence table stores immutable entry context, account,
  opening order, initial monetary risk, and confirmed closure. Existing databases
  acquire the new table through create_all; legacy tables are not rewritten.
- Outcomes include entry/exit commission, swap and fee, combine partial exits,
  and require fully closed volume. Reversals, multiple entries and ambiguous
  histories remain unlabelled. Pending known orders are retried after restart.
- Facts-only WIN/LOSS/BREAKEVEN memories are written atomically with the outcome.
  R = net PnL / initial monetary SL risk from fill price, volume and configured
  contract size; unavailable risk produces NULL, never an invented R.
- Legacy causal memories are preserved for audit but excluded from prompts and ML.
  Facts alone do not prove a liquidity trap or successful confluence. Per-trade
  score rewards/penalties are removed; validated strategy scores remain unchanged.
- ML reads only verified entry/outcome evidence, excludes breakeven from binary
  labels, splits chronologically, fits preprocessing inside each fold, purges
  overlapping label intervals, selects on walk-forward folds, then evaluates one
  selected model on an untouched final holdout against the rule-score baseline.
  Research artifacts remain disabled for trading, including after reload.

## Validation

Regression tests cover provider parsing, context wiring, Risk veto, PAPER/LIVE
order blocking, closed candles, history delays, partial exits, costs, unsupported
history shapes, account isolation, idempotency/restart recovery, factual labels,
R calculations, dataset construction, preprocessing leakage and label purging.
Bridge contract tests use mocked MT5 and httpx.MockTransport.

## Remaining boundaries

- These fixes do not establish an increase in win rate or profitability.
- No automatic model promotion or strategy parameter optimization is enabled.
- No retrospective recovery of trades that were never recorded by this app.
  Position identifiers differing from the opening order cannot be recovered from
  the pending-order fallback alone; a tracked position supplies its identifier.
  Netting/reversal/multiple-entry attribution needs a separate implementation.
- Real provider accuracy, rejected-candidate counterfactual outcomes, calibration,
  MFE/MAE, market-regime-conditioned comparisons and execution-cost stress tests
  still require a research dataset and separate validation.
- Full paper simulation, risk accounting and broker trade journaling remain
  separate project milestones; learning_evidence does not claim to replace them.


## Final verification — 2026-09-11

- Full mt5ai suite: 232 passed (175 existing datetime deprecation warnings).
- Separate mt5-bridge server tests: 2 passed.
- Shared R:R formulas corrected across five strategies, with patch-version bumps.
  BUY reward is TP minus entry; SELL reward is entry minus TP. The main pipeline
  recomputes the ratio before AI/Risk. Old performance figures need rerunning.
- Gemini uses the installed Antigravity CLI (`agy`) and its existing Google login.
  The evaluator requires schema-validated CLI output and fails closed when that
  output is unavailable or invalid. Vertex AI/gcloud and API-key integration were removed.
  Configure `AI_CLI_BIN=agy` only when the executable is not already on `PATH`.
- The deployment image installs both `codex` and `agy`. In Coolify, provide
  `CODEX_AUTH_JSON` as a secret for Codex/ChatGPT and `GEMINI_API_KEY` as a
  secret for Antigravity. The container entrypoint enables Antigravity's
  `gemini` provider without writing the API key to disk.
- Local portable Wine terminal attachment requires MT5_PATH plus MT5_PORTABLE=true.
  No account credentials were changed and no broker orders were sent during testing.

### Real-feed smoke result

Completed 2026-09-11 17:15 UTC against the existing Wine portable terminal:
`mode=paper`, `cycles=2`, `cycle_errors=0`, `symbol=XAUUSD`, 10 M5 candles
read, broker history endpoint reachable, zero open positions at the initial
snapshot. GPT returned structured analyses of actual candidates. Gemini remained
unavailable because the prior Gemini Snap CLI could not run from the Codex Snap
session, so Council failed closed. This verifies real-data analysis and shutdown, not broker fills or
future profitability. The localhost bridge was left running for the user.

Repeat with configured bridge settings:
`MT5_MODE=bridge python -m scripts.smoke_bridge_paper`
The script uses a temporary database, suppresses notifications and rejects every
broker mutation. Unit/integration fixtures exercise close outcomes and Risk veto.

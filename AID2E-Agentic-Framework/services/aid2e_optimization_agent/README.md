# AID2E Optimization Agent Helpers

The monitoring flow accumulates trial-scoped lifecycle events and generates one
factual sentence only when each trial reaches a successful or failed terminal
state. Each trial therefore creates one summary-model call and one summary
resource upload. Run and batch events remain available in the event journal but
do not create separate summaries. The sentence is compact L0-like orientation,
while complete event journals, framework logs, execution logs, checkpoints,
results, and Pareto fronts remain detailed L2 evidence.

Official OpenViking terminology is important: L0 is a short directory
abstract, L1 is a directory overview, and neither is a per-file memory tier.
Summary files are therefore archived as provenance-bearing resources. When the
installed OpenViking client supports sessions, the same records are committed
as a session so OpenViking can asynchronously extract genuine long-term memory.

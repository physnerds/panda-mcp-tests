# AID2E MCP Server

This server deliberately exposes only two tools:

- `aid2e_start_optimization` launches an explicitly authorized configuration;
- `aid2e_read_optimization` reads status and append-only events after a cursor.

Artifact upload, summarization, OpenViking sessions, and remote URIs are agent
responsibilities and are intentionally not AID2E MCP tools.

Configure the process with:

```bash
cd /path/to/AID2E-Agentic-Framework
source ./scripts/setup-aid2e-langchain-test.sh
export AID2E_REPOSITORY=/path/to/AID2E-framework
export AID2E_ALLOWED_CONFIG_ROOTS=/path/to/AID2E-framework/examples
export AID2E_ALLOWED_OUTPUT_ROOTS=/tmp/aid2e-agent-runs
export AID2E_COMMAND=/path/to/AID2E-framework/.venv/bin/aid2e
"$AID2E_AGENT_PYTHON" -m mcp_servers.aid2e.aid2e_mcp_server
```

From `mcp_servers/aid2e`, direct script execution is also supported:

```bash
"$AID2E_AGENT_PYTHON" aid2e_mcp_server.py
```

The default streamable-HTTP endpoint is `http://127.0.0.1:25902/mcp/`.
Run IDs are validated and duplicate runs are rejected. The server never uses a
shell, accepts arbitrary command arguments, stops runs, or alters AID2E state.

For environment setup and the complete launch-monitor-archive test, follow
`knowledge-base/AID2E-LangChain-End-to-End-Test-Runbook-2026-11-03T20-39-08-0500.md`
or run:

```bash
source ./scripts/setup-aid2e-langchain-test.sh
./scripts/run-aid2e-langchain-test.sh
```

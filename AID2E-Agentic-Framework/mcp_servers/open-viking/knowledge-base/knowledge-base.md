# OpenViking Knowledge Base Index

This file is the quick index for Markdown documents in this directory. Use it
to decide which file to read or ingest into OpenViking when future AID2E/PanDA
work needs context.

## Documents

### `open-viking-setup.md`

Setup and handoff summary for the OpenViking MCP integration in
`AID2E-Agentic-Framework`. Covers what was added so far, how
`openviking_client.py` talks to `https://aipanda106.cern.ch:443`, how
`openviking_mcp_server.py` exposes FastMCP tools on `localhost:25901/mcp`, how
to start the server, how to test tool discovery, and how to run direct client
smoke tests.

Keywords: OpenViking MCP, aipanda106, FastMCP, Codex config, tool discovery,
`openviking_client.py`, `openviking_mcp_server.py`, SSL, API key, streamable
HTTP, local wrapper, remote backend.

### `openviking_panda_integration_test_outline.md`

Detailed integration-test plan for using OpenViking as the knowledge and
evidence layer around AID2E multi-step PanDA/iDDS workflows. Rewritten from
GitHub issue `aid2e/AID2E-framework#60` and related comments. Captures the
fan-out/fan-in PanDA runner motivation, `panda_multistep` payload shape,
`one2one` and `all2one` dependency mapping, `results` versus `datasets`
handoff, PanDA-managed versus scheduler-managed dependencies, and the proposed
OpenViking evidence ingestion and verification flow.

Keywords: PanDA, iDDS, AID2E issue 60, multi-step runner, `panda_multistep`,
fan-out, fan-in, dRICH, simulation, reconstruction, analysis, objective
aggregation, one2one, all2one, result handoff, dataset handoff,
`parent_internal_id`, Rucio, integration test, evidence ingestion.

### `knowledge-base.md`

This index file. It lists each Markdown document in the knowledge-base
directory with a short summary and search keywords so OpenViking users and MCP
agents can quickly choose the right resource.

Keywords: index, knowledge base, resource discovery, OpenViking documents,
AID2E context.

# OpenViking MCP Setup

## What Has Been Done

The OpenViking work in `AID2E-Agentic-Framework` now has three pieces:

1. A direct Python client wrapper: `mcp_servers/open-viking/openviking_client.py`
2. A FastMCP server wrapper: `mcp_servers/open-viking/openviking_mcp_server.py`
3. Codex/AID2E configuration and routing notes: `.codex/config.toml`, `.codex/mcp_servers/openviking.toml`, and `agent/tool_instructions/openviking_*.md`

The direct client connects to the remote OpenViking backend:

```text
https://aipanda106.cern.ch:443
```

The MCP server is a local wrapper process. By default it listens on:

```text
http://localhost:25901/mcp
```

When an MCP client calls an `openviking_*` tool, the local MCP server creates an
`OpenVikingAipandaClient`, authenticates with the OpenViking API key, and calls
the aipanda OpenViking service.

## MCP Tools

The MCP server exposes:

- `openviking_find`: semantic search over indexed resources.
- `openviking_ls`: list `viking://` resource directories.
- `openviking_read`: read exact resource content.
- `openviking_abstract`: retrieve an L0 abstract for a resource.
- `openviking_overview`: retrieve an L1 overview for a resource or subtree.
- `openviking_add_resource`: ingest a local filesystem resource.

Tool results are JSON-friendly envelopes with `ok`, `operation`, `arguments`,
and `data`. Failures include `ok: false`, `isError: true`, and a structured
`error` object. This shape is intended to work cleanly with
`agent/BaseAgent.py` result normalization.

## Environment

Use the project Python interpreter:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python
```

Load OpenViking runtime variables from the repo root:

```bash
cd /home/amitbashyal/Documents/BNL-AiD2E/mcp-server/AID2E-Agentic-Framework
source ./openviking-variables.sh
```

The variables script sets:

- `OPENVIKING_URL`, default `https://aipanda106.cern.ch:443`
- `OPENVIKING_API_KEY_FILE`, default `mcp_servers/open-viking/.api_key`
- `OPENVIKING_MCP_HOST`, default `0.0.0.0`
- `OPENVIKING_MCP_PORT`, default `25901`
- `OPENVIKING_MCP_TRANSPORT`, default `streamable-http`
- `OPENVIKING_REQUIRE_SSL_ENV`, default `1`
- `SSL_CERT_FILE`, when neither `SSL_CERT_FILE` nor `SSL_CERT_DIR` is set

The SSL certificate can also be loaded from the OpenViking directory:

```bash
cd mcp_servers/open-viking
source set_ssl.sh
```

## Run The MCP Server

From the repo root:

```bash
cd /home/amitbashyal/Documents/BNL-AiD2E/mcp-server/AID2E-Agentic-Framework
source ./openviking-variables.sh
cd mcp_servers/open-viking
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python openviking_mcp_server.py
```

Expected endpoint:

```text
http://localhost:25901/mcp
```

If the MCP server runs on `aipanda`, either point Codex/AID2E at the reachable
HTTP endpoint or create an SSH tunnel so the local Codex process can use
`http://localhost:25901/mcp`.

## Test MCP Tool Discovery

In another terminal:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python -c "import asyncio
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

async def main():
    async with Client(transport=StreamableHttpTransport(url='http://localhost:25901/mcp')) as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools])

asyncio.run(main())"
```

Expected tool names:

```text
openviking_find
openviking_ls
openviking_read
openviking_abstract
openviking_overview
openviking_add_resource
```

A plain `curl http://localhost:25901/mcp` can return HTTP 406 because the
streamable MCP endpoint expects an `Accept: text/event-stream` capable client.
Use a FastMCP client for a real discovery test.

## Test Directly With `openviking_client.py`

From the OpenViking directory:

```bash
cd /home/amitbashyal/Documents/BNL-AiD2E/mcp-server/AID2E-Agentic-Framework/mcp_servers/open-viking
source set_ssl.sh
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python openviking_client.py ls
```

Search:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python openviking_client.py find "how to use openviking" --limit 5
```

Read an exact resource URI discovered by `ls` or `find`:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python openviking_client.py read "viking://resources/path/to/resource.md"
```

Get summaries:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python openviking_client.py abstract "viking://resources/path/to/resource.md"
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python openviking_client.py overview "viking://resources/path/to/resource.md"
```

Add a local resource:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python openviking_client.py add-resource ./knowledge-base/open-viking-setup.md --wait
```

Do not ingest secrets, tokens, private keys, private certificates, or
unsanitized logs.

## Codex Configuration

Codex reads `.codex/config.toml`. This repo keeps MCP server definitions in
fragments under `.codex/mcp_servers/` and renders the single file Codex expects:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python .codex/render_config.py
```

The OpenViking fragment is:

```text
.codex/mcp_servers/openviking.toml
```

Restart Codex after regenerating the config so `/mcp` refreshes its server and
tool list.

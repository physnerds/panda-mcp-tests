# OpenViking MCP Server

`openviking_mcp_server.py` exposes the aipanda OpenViking service as FastMCP
tools:

- `openviking_find`
- `openviking_ls`
- `openviking_read`
- `openviking_abstract`
- `openviking_overview`
- `openviking_add_resource`

Before starting it, configure the CERN CA and API key:

```bash
cd mcp_servers/open-viking
source set_ssl.sh
export OPENVIKING_API_KEY_FILE="$PWD/.api_key"
```

Start the streamable HTTP MCP endpoint:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python openviking_mcp_server.py
```

By default the server listens on:

```text
http://0.0.0.0:25901/mcp/
```

Useful environment overrides:

- `OPENVIKING_URL`: OpenViking backend URL, default `https://aipanda106.cern.ch:443`
- `OPENVIKING_API_KEY_FILE`: API key file, default `.api_key` in this directory
- `OPENVIKING_REQUIRE_SSL_ENV`: set to `0` to skip the SSL environment check
- `OPENVIKING_MCP_HOST`: MCP bind host, default `0.0.0.0`
- `OPENVIKING_MCP_PORT`: MCP port, default `25901`
- `OPENVIKING_MCP_TRANSPORT`: FastMCP transport, default `streamable-http`

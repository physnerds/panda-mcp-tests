# Launching Codex With AID2E MCP Tools

This runbook starts a Codex session with three AID2E MCP surfaces:

- `swf-testbed`: remote PanDA-SWF monitor tools from `https://pandaserver02.sdcc.bnl.gov:8443/swf-monitor/mcp/`
- `openviking`: local OpenViking MCP wrapper on `http://localhost:25901/mcp`
- `panda-idds`: local Docker-backed PanDA/iDDS MCP wrapper on `http://localhost:25888/mcp/`

The setup follows the MCP-first architecture in `MULTI_AGENT_GUIDE.md`: Codex is the MCP client, while this repo provides MCP servers, tool schemas, credentials, and compact tool routing notes.

## 1. Open Shells From The Repo Root

Use this checkout as the working directory:

```bash
cd /home/amitbashyal/Documents/BNL-AiD2E/mcp-server/AID2E-Agentic-Framework
export AID2E_REPO="$PWD"
export AID2E_PYTHON="/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python"
```

Use the project interpreter for OpenViking and AID2E checks:

```bash
"$AID2E_PYTHON" --version
```

## 2. Set Credential And Runtime Variables

### SWF Monitor

The SWF endpoint is reached through an SSH tunnel to SDCC. Codex sends the bearer token from `SWF_MONITOR_MCP_TOKEN`.

```bash
export SWF_MONITOR_MCP_TOKEN="$(tr -d '\r\n' < "$AID2E_REPO/.token-swf")"
```

If the SDCC grid certificates are not already local, copy them once:

```bash
rsync -av rcfsub:/etc/grid-security/certificates/ "$HOME/sdcc-grid-certificates/"
```

Then set:

```bash
export SSL_CERT_DIR="$HOME/sdcc-grid-certificates"
```

### OpenViking

Load the OpenViking environment from the repo helper:

```bash
source "$AID2E_REPO/openviking-variables.sh"
```

This sets the OpenViking backend URL, API key file, MCP host/port, transport, and SSL variables. The default API key file is:

```text
mcp_servers/open-viking/.api_key
```

### PanDA/iDDS

The Docker launcher reads `mcp_servers/panda-idds-server/.token` and injects the OIDC token into the container. Codex should also send the same token to the MCP wrapper as a bearer token:

```bash
export PANDA_IDDS_MCP_TOKEN="$("$AID2E_PYTHON" -c "import json; print(json.load(open('$AID2E_REPO/mcp_servers/panda-idds-server/.token'))['id_token'])")"
export PANDA_AUTH_VO="${PANDA_AUTH_VO:-EIC}"
```

Do not print or commit `.token`, `.token-swf`, `.api_key`, bearer tokens, private keys, or certificates.

## 3. Start The SWF Tunnel

In a dedicated terminal, keep this process running:

```bash
ssh -N -L 8443:pandaserver02.sdcc.bnl.gov:443 rcfsub
```

For the TLS certificate name to match the tunneled endpoint, add the host alias while testing:

```bash
sudo sh -c 'echo "127.0.0.1 pandaserver02.sdcc.bnl.gov" >> /etc/hosts'
```

The SWF MCP endpoint used by Codex is:

```text
https://pandaserver02.sdcc.bnl.gov:8443/swf-monitor/mcp/
```

When finished, remove the temporary host alias:

```bash
sudo sed -i.bak '/pandaserver02.sdcc.bnl.gov/d' /etc/hosts
```

## 4. Start The OpenViking MCP Server

In a second terminal:

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

Expected tools:

```text
openviking_find
openviking_ls
openviking_read
openviking_abstract
openviking_overview
openviking_add_resource
```

## 5. Start The PanDA/iDDS MCP Server

In a third terminal:

```bash
cd /home/amitbashyal/Documents/BNL-AiD2E/mcp-server/AID2E-Agentic-Framework/mcp_servers/panda-idds-server
./recreate_docker_bnl.sh
```

The script creates or replaces the `panda-mcp` Docker container, copies `server-files/mcp_main.py`, `server-files/mcp_utils.py`, `server-files/panda_server_config.json`, and `server-files/panda_mcp_endpoints.json`, then exposes:

```text
http://localhost:25888/mcp/
```

The configured PanDA/iDDS tools are:

```text
is_alive
get_user_attributes
get_status
get_description
get_available_event_range_count
```

Useful checks:

```bash
sudo docker ps | grep panda-mcp
sudo docker exec panda-mcp env | grep PANDA_AUTH
sudo docker exec panda-mcp tail -f /var/log/panda/panda_mcp_stderr.log
```

## 6. Render The Codex MCP Config

Codex reads a single `config.toml`. This repo keeps MCP server definitions in `.codex/mcp_servers/*.toml` and renders the combined file.

From the repo root:

```bash
cd /home/amitbashyal/Documents/BNL-AiD2E/mcp-server/AID2E-Agentic-Framework
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python .codex/render_config.py
```

The source fragments are:

```text
.codex/mcp_servers/openviking.toml
.codex/mcp_servers/panda-idds.toml
.codex/mcp_servers/swf-testbed.toml
```

The rendered file is:

```text
.codex/config.toml
```

## 7. Launch Codex With The AID2E Config

Start Codex from a shell that has the variables from step 2. Point `CODEX_HOME` at this repo's `.codex` directory so Codex loads the rendered config:

```bash
cd /home/amitbashyal/Documents/BNL-AiD2E/mcp-server/AID2E-Agentic-Framework
export CODEX_HOME="$PWD/.codex"
codex -C "$PWD"
```

Inside Codex, run:

```text
/mcp
```

Confirm these servers appear:

```text
openviking
panda-idds
swf-testbed
```

If tools are missing, restart Codex after rerunning `.codex/render_config.py` and confirm the relevant server process or tunnel is still running.

## 8. Smoke-Test Tool Access

Use small read-only prompts first:

```text
List the available MCP servers and tools.
Use the openviking_ls tool to list the top-level OpenViking resources.
Use the panda-idds is_alive tool.
Use swf-testbed panda_get_activity for the last day.
```

For PanDA job or task troubleshooting, prefer MCP-provider surfaces with exact JSON tool calls and structured results. Use OpenViking search/read tools for documentation grounding, SWF tools for PanDA-SWF monitor state, and PanDA/iDDS tools for server API checks.

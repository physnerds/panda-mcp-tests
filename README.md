# PanDA MCP Agent

Minimal setup and usage guide for the PanDA MCP client in this repository.

## What is in this repo

- `mcp_agent.py`: natural-language client that talks to a PanDA MCP server
- `mcp_test_client.py`: direct tool test client
- `panda_server_config.json`: PanDA MCP server config
- `panda_mcp_endpoints.json`: exposed MCP tools/endpoints
- `recreate_docker.sh`: recreate local `panda-mcp` Docker container

## Requirements

- Python 3.11+
- Docker
- Access to `sudo docker` on your machine

Install Python deps for the client:

```bash
python3 -m venv panda-mcp
source panda-mcp/bin/activate
pip install fastmcp requests
```

## Local MCP Installation (Docker)

Use the provided script:

```bash
chmod +x recreate_docker.sh
./recreate_docker.sh
```

What this does:

1. Stops/removes existing `panda-mcp` container (if present)
2. Creates `panda-mcp` from `ghcr.io/pandawms/panda-server:latest`
3. Exposes local MCP port `25888`
4. Sets PanDA API env vars to CERN PanDA server:
   - `PANDA_API_URL=http://pandaserver.cern.ch:25080/api/v1`
   - `PANDA_API_URL_SSL=https://pandaserver.cern.ch:25443/api/v1`
5. Copies config files into the container:
   - `panda_server_config.json`
   - `panda_mcp_endpoints.json`
6. Restarts container to apply config

## Verify

```bash
source panda-mcp/bin/activate
python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http
```

## Mistral (Ollama) Setup

This project uses Ollama for the LLM backend, with `mistral` as the default model in `mcp_agent.py`.

1. Install Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

2. Start the Ollama server:

```bash
ollama serve
```

3. Download the Mistral model:

```bash
ollama pull mistral
```

4. Verify the model is available:

```bash
ollama list
```

You should see `mistral` in the list.

## Run the Agent

```bash
source panda-mcp/bin/activate
python mcp_agent.py --server docker
```

Optional flags:

- `--mcp-url http://localhost:25888/mcp/`
- `--model mistral` (enables Mistral; this is the default)
- `--ollama_url http://localhost:11434`
- `--token <oidc_token>` (for write operations)
- `--vo <virtual_org>`

## Configure Exposed Tools

Edit `panda_mcp_endpoints.json`, then apply changes:

```bash
sudo docker cp panda_mcp_endpoints.json panda-mcp:/opt/panda/etc/panda/
sudo docker restart panda-mcp
```

## References

- PanDA docs: https://panda-wms.readthedocs.io/
- PanDA MCP docs: https://panda-wms.readthedocs.io/en/latest/advanced/mcp.html
- Model Context Protocol: https://modelcontextprotocol.io/

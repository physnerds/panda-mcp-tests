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

## Using vLLM (Perlmutter)

For more powerful inference using the Llama-3.3-70B-Instruct model hosted on Perlmutter, you can use vLLM instead of Ollama.

### 1. Set Up SSH Tunnel to Perlmutter

First, establish an SSH tunnel to access the vLLM server running on Perlmutter:

```bash
ssh -L 8000:localhost:8000 perlmutter.nersc.gov
```

This forwards port 8000 from Perlmutter to your local machine.

### 2. Run the Agent with vLLM

```bash
source panda-mcp/bin/activate
python mcp_agent.py --server docker --use_vllm --vllm_url http://localhost:8000/v1/completions
```

Optional vLLM flags:

- `--use_vllm`: Enable vLLM instead of Ollama
- `--vllm_url http://localhost:8000/v1/completions`: vLLM server URL (default shown)

### Key Differences: Ollama vs vLLM

| Feature | Ollama | vLLM |
|---------|--------|------|
| **API Style** | Chat-based (`/api/chat`) | Completions (`/v1/completions`) |
| **Model** | mistral (default) | Llama-3.3-70B-Instruct |
| **Location** | Local | Perlmutter NERSC |
| **Message Format** | Message history objects | Single prompt string |
| **Performance** | Good for local testing | Better for complex reasoning |

The agent automatically handles the different API formats when switching between backends.

### Testing vLLM Connection

You can test the vLLM connection independently using the test script:

```bash
python test-perlmutter-inference.py
```

## References

- PanDA docs: https://panda-wms.readthedocs.io/
- PanDA MCP docs: https://panda-wms.readthedocs.io/en/latest/advanced/mcp.html
- Model Context Protocol: https://modelcontextprotocol.io/

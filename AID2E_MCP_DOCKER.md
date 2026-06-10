# AID2E MCP Docker Setup

This document summarizes the current AID2E MCP Docker workflow.

The Docker image installs the AID2E framework from:

- Repository: `https://github.com/aid2e/AID2E-framework.git`
- Branch: `testing-pymoo-models`
- Dockerfile: `Dockerfile.aid2e`
- MCP service source: `extracted/aid2e_server/aid2e_service/`
- MCP endpoint: `http://localhost:25887/mcp`

## What The Image Contains

The image is based on `python:3.11-slim`.

At build time it:

1. Installs system build dependencies and `git`.
2. Creates a Python virtual environment at `/opt/aid2e-venv`.
3. Clones AID2E into `/opt/AID2E-framework`.
4. Installs AID2E into the virtual environment.
5. Installs MCP server runtime dependencies: `mcp`, `starlette`, and `uvicorn`.
6. Copies the local AID2E MCP service package into `/app/aid2e_service`.

At runtime it starts:

```bash
uvicorn aid2e_service.asgi:application --host 0.0.0.0 --port ${MCP_PORT}
```

The default MCP port is `25887`.

## Build The Image

From the repository root:

```bash
sudo docker build -f Dockerfile.aid2e -t aid2e-mcp:latest .
```

To install optional AID2E extras:

```bash
sudo docker build -f Dockerfile.aid2e \
  --build-arg AID2E_INSTALL_EXTRAS=all \
  -t aid2e-mcp:latest .
```

## Verify AID2E CLI In The Image

This checks that the image has the `aid2e` command installed:

```bash
sudo docker run --rm aid2e-mcp:latest aid2e --help
```

Expected result: AID2E prints its CLI help with commands such as `describe`,
`inspect`, `list`, `optimize`, `validate`, and `version`.

## Run The MCP Server

Start the MCP server in the background:

```bash
sudo docker run --rm -d \
  --name aid2e-mcp \
  -p 25887:25887 \
  aid2e-mcp:latest
```

Check that the container is running:

```bash
sudo docker ps --filter name=aid2e-mcp
sudo docker logs aid2e-mcp
```

Restart cleanly:

```bash
sudo docker rm -f aid2e-mcp
sudo docker run --rm -d \
  --name aid2e-mcp \
  -p 25887:25887 \
  aid2e-mcp:latest
```

## Run With A Work Directory

AID2E optimization jobs need a place for config files, scripts, and outputs.
The MCP tools default to `/work` inside the container.

Create and mount a local work directory:

```bash
mkdir -p aid2e-work

sudo docker run --rm -d \
  --name aid2e-mcp \
  -p 25887:25887 \
  -v "$PWD/aid2e-work:/work" \
  aid2e-mcp:latest
```

Files placed in local `aid2e-work/` are visible inside the container at `/work`.

## Test With The MCP Client

The test client in this repository is named `mcp_test_client.py`.

Run a basic tool test:

```bash
python mcp_test_client.py \
  --host localhost \
  --port 25887 \
  --use_http \
  --tool aid2e_version
```

List available MCP tools and call AID2E top-level help:

```bash
python mcp_test_client.py \
  --host localhost \
  --port 25887 \
  --use_http \
  --tool aid2e_help
```

Call subcommand help:

```bash
python mcp_test_client.py \
  --host localhost \
  --port 25887 \
  --use_http \
  --tool aid2e_help \
  --kv command=list
```

## MCP Tools Exposed

The AID2E MCP service currently exposes:

- `aid2e_version`: runs `aid2e version`.
- `aid2e_help`: runs `aid2e --help` or `aid2e <command> --help`.
- `aid2e_list`: runs `aid2e list`, optionally with a list category.
- `aid2e_run`: runs arbitrary AID2E CLI arguments without using a shell.

`aid2e_run` is intended for commands such as:

```python
["validate", "config.yaml"]
["describe", "config.yaml"]
["optimize", "config.yaml"]
```

## Useful Debug Commands

Show logs:

```bash
sudo docker logs aid2e-mcp
```

Open a shell in the running container:

```bash
sudo docker exec -it aid2e-mcp bash
```

Check AID2E inside the running container:

```bash
sudo docker exec aid2e-mcp aid2e --help
sudo docker exec aid2e-mcp aid2e version
```

Stop the server:

```bash
sudo docker rm -f aid2e-mcp
```

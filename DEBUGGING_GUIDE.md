# Authored with Claude
# PanDA MCP Server - Debugging Guide

## Table of Contents
1. [Overview](#overview)
2. [How PanDA MCP Works](#how-panda-mcp-works)
3. [Issues Discovered & Solutions](#issues-discovered--solutions)
4. [Debugging Tools & Techniques](#debugging-tools--techniques)
5. [Testing Procedures](#testing-procedures)

---

## Overview

This document chronicles the debugging process for setting up a PanDA MCP server in Docker that communicates with the BNL SDCC PanDA server using OIDC authentication.

**Final Result**: Successfully established MCP server communication with BNL SDCC PanDA server using OIDC tokens.

---

## How PanDA MCP Works

### Architecture

```
┌─────────────────┐         ┌──────────────────────┐         ┌─────────────────────┐
│  MCP Client     │  HTTP   │  MCP Server          │  HTTP   │  PanDA API Server   │
│  (mcp_test_     │ ──────> │  (Docker Container)  │ ──────> │  (BNL SDCC)        │
│   client.py)    │         │  Port: 25888         │         │  pandaserver01...  │
└─────────────────┘         └──────────────────────┘         └─────────────────────┘
      │                              │                                │
      │                              │                                │
      v                              v                                v
  - Sends OIDC token         - FastMCP framework           - Validates OIDC token
  - Calls tools             - Wraps PanDA API tools        - Returns JSON responses
  - Gets results            - Routes requests               - Requires correct paths
```

### Communication Flow

1. **Client → MCP Server**
   - Client connects via HTTP/HTTPS to `localhost:25888/mcp`
   - Transport: `streamable-http` (FastMCP protocol)
   - Authentication headers:
     - `Authorization: Bearer <OIDC_token>`
     - `Origin: <VO_name>` (e.g., "EIC")

2. **MCP Server Processing**
   - FastMCP receives request and extracts headers using `get_http_headers()`
   - `mcp_utils.py:create_tool()` wraps each PanDA API function
   - Extracts authentication from headers:
     - `id_token` from `Authorization: Bearer ...`
     - `auth_vo` from `Origin` header
   - Creates `HttpClient` instance and calls `override_oidc()`

3. **MCP Server → PanDA API**
   - `HttpClient` makes HTTP request to PanDA API
   - URL format: `http://pandaserver01.sdcc.bnl.gov:25080/api/v1/{module}/{function}`
   - Headers sent:
     - `Accept: application/json`
     - `Content-Type: application/json`
     - `Authorization: Bearer <token>`
     - `Origin: <VO>`

4. **Response Path**
   - PanDA API validates token and returns JSON
   - MCP server wraps response in MCP protocol format
   - Client receives structured response

### Key Components

#### 1. Docker Container
- **Image**: `ghcr.io/pandawms/panda-server:latest`
- **Environment Variables**:
  ```bash
  PANDA_API_URL=http://pandaserver01.sdcc.bnl.gov:25080/api/v1
  PANDA_API_URL_SSL=https://pandaserver01.sdcc.bnl.gov:25443/api/v1
  PANDA_AUTH=oidc
  PANDA_AUTH_ID_TOKEN=<token>
  PANDA_AUTH_VO=EIC
  ```

#### 2. MCP Server (mcp_main.py)
- FastMCP server running on `0.0.0.0:25888`
- Loads API endpoints from `panda_mcp_endpoints.json`
- Creates tools by importing PanDA API modules
- **Critical Fix**: Changed module path from `server.panda.api.v1` to `api.v1`

#### 3. Tool Wrapper (mcp_utils.py)
- Wraps PanDA API functions as MCP tools
- Extracts authentication from HTTP headers
- Configures `HttpClient` with OIDC credentials
- Routes calls to appropriate PanDA API endpoints

#### 4. HTTP Client (http_client.py)
- Handles HTTP requests to PanDA API
- Supports both X.509 and OIDC authentication
- `override_oidc()` method sets authentication parameters

---

## Issues Discovered & Solutions

### Issue 1: MCP Process Not Running
**Symptom**: 
- Container started but MCP service wasn't listening on port 25888
- `pgrep -af mcp_main` showed no process
- PID file created but process died immediately

**Root Cause**: Invalid JSON in `panda_server_config.json` - missing closing brace `}`

**Solution**:
```json
{
  "mcp": {
    "transport": "http",
    "endpoint_list_file": "/opt/panda/etc/panda/panda_mcp_endpoints.json"
  }
}
```

**Test**:
```bash
sudo docker exec panda-mcp python3 -m json.tool /opt/panda/etc/panda/config_json/panda_server_config.json
```

---

### Issue 2: Wrong Python Module Path
**Symptom**:
- MCP process started but hung during initialization
- No stdout/stderr output
- High CPU usage but no port listening

**Root Cause**: 
`mcp_main.py` parsed API URL to construct module path:
- URL: `http://pandaserver01.sdcc.bnl.gov:25080/server/panda/api/v1`
- Generated path: `server.panda.api.v1` (WRONG)
- Actual module: `api.v1` (CORRECT)

**Solution**: Fixed in `mcp_main.py`:
```python
# OLD (extracted from URL):
# p = urlparse(api_url)
# api_module_path = ".".join([seg for seg in p.path.strip("/").split("/") if seg])

# NEW (hardcoded correct path):
api_module_path = "api.v1"
```

**Test**:
```bash
sudo docker exec panda-mcp bash -c 'source /opt/panda/bin/activate && \
  timeout 10 python3 /opt/panda/lib/python3.11/site-packages/pandaserver/pandamcp/mcp_main.py'
```

---

### Issue 3: Import Blocking
**Symptom**:
- `import_module(f"pandaserver.{api_module_path}.{mod}_api")` hung indefinitely
- Process consumed CPU but never completed startup

**Root Cause**: Attempting to import `pandaserver.server.panda.api.v1.system_api` (non-existent module)

**Verification**:
```bash
# This works:
python3 -c "from pandaserver.api.v1 import system_api; print('Success')"

# This hangs:
python3 -c "from pandaserver.server.panda.api.v1 import system_api"
```

**Solution**: Same as Issue 2 - corrected module path

---

### Issue 4: Connection Reset by Peer
**Symptom**:
- Port 25888 listening
- TCP connection established
- Connection immediately reset: `curl: (56) Recv failure: Connection reset by peer`

**Root Cause**: Server accepted connection but crashed when processing HTTP request (due to import failure)

**Solution**: Fixed module import path (Issue 2)

---

### Issue 5: HTTP 406 Not Acceptable
**Symptom**:
After fixing imports, plain HTTP requests returned:
```
HTTP/1.1 406 Not Acceptable
content-type: application/json
mcp-session-id: ce1d9e91ca9e417f8f2a14c9172c069a
```

**Root Cause**: FastMCP protocol requires specific MCP message format, not plain HTTP GET/POST

**Not an Issue**: This is expected behavior. MCP clients must use the MCP protocol.

**Test**:
```bash
# Plain GET fails (expected):
curl http://localhost:25888/mcp

# MCP client works:
python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http
```

---

### Issue 6: 403 Forbidden from PanDA API
**Symptom**:
- MCP server running correctly
- Client connects successfully
- Tools called but returned: `403 Client Error: Forbidden`

**Root Cause**: Wrong API endpoint URL

**Investigation**:
```bash
# This FAILED (403):
curl -H "Authorization: Bearer $TOKEN" -H "Origin: EIC" \
  http://pandaserver01.sdcc.bnl.gov:25080/server/panda/api/v1/system/is_alive

# This WORKED (200):
curl -H "Authorization: Bearer $TOKEN" -H "Origin: EIC" \
  http://pandaserver01.sdcc.bnl.gov:25080/api/v1/system/is_alive
```

**Solution**: Updated environment variables:
```bash
# OLD:
PANDA_API_URL=http://pandaserver01.sdcc.bnl.gov:25080/server/panda/api/v1

# NEW:
PANDA_API_URL=http://pandaserver01.sdcc.bnl.gov:25080/api/v1
```

---

## Debugging Tools & Techniques

### 1. Container Diagnostics

#### Check Container Status
```bash
# List running containers
sudo docker ps --filter "name=panda-mcp"

# Check if container exists but stopped
sudo docker ps -a --filter "name=panda-mcp"

# View container logs
sudo docker logs --tail 50 panda-mcp
sudo docker logs -f panda-mcp  # Follow logs
```

#### Check Process Status Inside Container
```bash
# Check if MCP process is running
sudo docker exec panda-mcp pgrep -af mcp_main

# Check process details
sudo docker exec panda-mcp ps aux | grep mcp

# Check PID file
sudo docker exec panda-mcp cat /var/log/panda/panda_mcp.pid
```

#### Clean Up Stale Processes
```bash
# Kill zombie processes
sudo docker exec panda-mcp pkill -9 -f mcp_main.py

# Remove stale PID file
sudo docker exec panda-mcp rm -f /var/log/panda/panda_mcp.pid
```

---

### 2. Network Diagnostics

#### Check Port Listening (Inside Container)
```bash
# Using netstat
sudo docker exec panda-mcp netstat -tlnp | grep 25888

# Using ss (modern alternative)
sudo docker exec panda-mcp ss -tlnp | grep 25888

# Using lsof
sudo docker exec panda-mcp lsof -i :25888
```

#### Check Port Listening (On Host)
```bash
# Check if port is accessible from host
netstat -tuln | grep 25888
ss -tuln | grep 25888

# Check Docker port mapping
sudo docker port panda-mcp
```

#### Test Connectivity
```bash
# Test from inside container
sudo docker exec panda-mcp curl -v http://localhost:25888/mcp

# Test from host
curl -v http://localhost:25888/mcp

# Test basic TCP connectivity
timeout 2 bash -c "echo > /dev/tcp/localhost/25888"
```

---

### 3. Python Import Debugging

#### Test Individual Imports
```bash
sudo docker exec panda-mcp bash -c 'source /opt/panda/bin/activate && \
  python3 -c "from pandaserver.api.v1 import system_api; print(\"Success\")"'
```

#### Find Module Location
```bash
sudo docker exec panda-mcp bash -c 'source /opt/panda/bin/activate && \
  python3 -c "import pandaserver.api.v1.system_api as m; print(m.__file__)"'
```

#### Test Module Loading with Timeout
```bash
sudo docker exec panda-mcp bash -c 'source /opt/panda/bin/activate && \
  timeout 10 python3 -c "from pandaserver.api.v1 import system_api"'
```

---

### 4. Configuration Validation

#### Validate JSON Files
```bash
# Check JSON syntax
sudo docker exec panda-mcp bash -c 'source /opt/panda/bin/activate && \
  python3 -m json.tool /opt/panda/etc/panda/config_json/panda_server_config.json'

# Check endpoints file
sudo docker exec panda-mcp cat /opt/panda/etc/panda/panda_mcp_endpoints.json | python3 -m json.tool
```

#### Check Environment Variables
```bash
# List all PANDA variables
sudo docker exec panda-mcp env | grep PANDA

# Check specific variables
sudo docker exec panda-mcp printenv PANDA_AUTH
sudo docker exec panda-mcp printenv PANDA_API_URL
sudo docker exec panda-mcp printenv PANDA_AUTH_ID_TOKEN | head -c 50
```

---

### 5. Log Analysis

#### View MCP Logs
```bash
# Standard output
sudo docker exec panda-mcp cat /var/log/panda/panda_mcp_stdout.log

# Standard error (most useful for debugging)
sudo docker exec panda-mcp cat /var/log/panda/panda_mcp_stderr.log

# Follow logs in real-time
sudo docker exec panda-mcp tail -f /var/log/panda/panda_mcp_stderr.log

# Check all PanDA logs
sudo docker exec panda-mcp ls -lh /var/log/panda/
```

#### Add Debug Logging
Add print statements with `flush=True` to ensure immediate output:
```python
print(f"DEBUG: Variable value = {value}", file=sys.stderr, flush=True)
```

---

### 6. MCP Server Testing

#### Run MCP Server in Foreground
```bash
sudo docker exec panda-mcp bash -c 'source /opt/panda/bin/activate && \
  timeout 10 python3 -u /opt/panda/lib/python3.11/site-packages/pandaserver/pandamcp/mcp_main.py'
```

#### Test with Debug Script
```bash
sudo docker exec panda-mcp bash -c 'source /opt/panda/bin/activate && \
  python3 << "EOF"
# Add test code here
from pandaserver.api.v1.http_client import HttpClient
client = HttpClient()
print(f"Client created: {type(client)}")
EOF
'
```

---

### 7. Authentication Testing

#### Test OIDC Token
```bash
# Check token validity (decode JWT)
sudo docker exec panda-mcp bash -c '
python3 << "EOF"
import os, json, base64
from datetime import datetime

token = os.getenv("PANDA_AUTH_ID_TOKEN")
payload = token.split(".")[1]
payload += "=" * ((4 - len(payload) % 4) % 4)
decoded = json.loads(base64.urlsafe_b64decode(payload))
print(json.dumps(decoded, indent=2))

exp = datetime.fromtimestamp(decoded["exp"])
print(f"\nExpires: {exp}")
print(f"Valid: {exp > datetime.now()}")
EOF
'
```

#### Test API Endpoint with Token
```bash
sudo docker exec panda-mcp bash -c '
TOKEN=$(printenv PANDA_AUTH_ID_TOKEN)
curl -s -H "Authorization: Bearer $TOKEN" -H "Origin: EIC" \
  http://pandaserver01.sdcc.bnl.gov:25080/api/v1/system/is_alive | python3 -m json.tool
'
```

#### Test HttpClient with OIDC
```bash
sudo docker exec panda-mcp bash -c 'source /opt/panda/bin/activate && \
python3 << "EOF"
import os
from pandaserver.api.v1.http_client import HttpClient

client = HttpClient()
token = os.getenv("PANDA_AUTH_ID_TOKEN")
client.override_oidc(True, token, "EIC")

url = "http://pandaserver01.sdcc.bnl.gov:25080/api/v1/system/is_alive"
status, output = client.get(url, {})
print(f"Status: {status}, Output: {output}")
EOF
'
```

---

### 8. MCP Client Testing

#### Basic Tool Call
```bash
source panda-mcp/bin/activate
python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http
```

#### Verbose Mode with Token
```bash
python mcp_test_client.py \
  --tool is_alive \
  --host localhost \
  --port 25888 \
  --use_http \
  --vo EIC \
  -v
```

#### List Available Tools
```bash
# Connect and list tools without calling them
python mcp_test_client.py --tool list --host localhost --port 25888 --use_http
```

---

### 9. Diagnostic Scripts Created

#### diagnose_mcp_docker.sh
Comprehensive diagnostic script that checks:
- Container status
- Process status
- Port binding
- Configuration files
- Log files
- HTTP connectivity

Usage:
```bash
./diagnose_mcp_docker.sh
```

#### fix_mcp_startup.sh
Attempts to fix common startup issues:
- Clean stale PID files
- Restart service
- Verify process running
- Test connectivity

---

### 10. Useful Docker Commands

#### Enter Container
```bash
# Interactive shell
sudo docker exec -it panda-mcp bash

# Run command as root
sudo docker exec -u root panda-mcp <command>
```

#### Copy Files
```bash
# Copy from host to container
sudo docker cp local_file.txt panda-mcp:/tmp/

# Copy from container to host
sudo docker cp panda-mcp:/var/log/panda/panda_mcp_stderr.log ./
```

#### Restart Services
```bash
# Restart MCP service
sudo docker exec panda-mcp /etc/rc.d/init.d/panda-mcp restart

# Restart entire container
sudo docker restart panda-mcp
```

---

## Testing Procedures

### Pre-Flight Checks

1. **Verify Token Validity**
   ```bash
   python3 -c "import json; from datetime import datetime; \
     token = json.load(open('.token')); \
     exp = datetime.fromtimestamp(token['expires_at']); \
     print(f'Expires: {exp}'); print(f'Valid: {exp > datetime.now()}')"
   ```

2. **Test API Endpoint Directly**
   ```bash
   TOKEN=$(python3 -c "import json; print(json.load(open('.token'))['id_token'])")
   curl -s -H "Authorization: Bearer $TOKEN" -H "Origin: EIC" \
     http://pandaserver01.sdcc.bnl.gov:25080/api/v1/system/is_alive
   ```

### Container Health Check

1. **Check Container is Running**
   ```bash
   sudo docker ps | grep panda-mcp
   ```

2. **Check MCP Process**
   ```bash
   sudo docker exec panda-mcp pgrep -af mcp_main
   ```

3. **Check Port Listening**
   ```bash
   sudo docker exec panda-mcp netstat -tlnp | grep 25888
   ```

4. **Test HTTP Endpoint**
   ```bash
   curl -v http://localhost:25888/mcp 2>&1 | grep "HTTP"
   ```

### MCP Client Test Suite

1. **Test is_alive (No Auth Required)**
   ```bash
   python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http
   ```

2. **Test get_user_attributes (Auth Required)**
   ```bash
   python mcp_test_client.py --tool get_user_attributes --host localhost --port 25888 --use_http
   ```

3. **Test with Invalid Token (Should Fail)**
   ```bash
   # Temporarily corrupt token
   sudo docker exec panda-mcp bash -c 'export PANDA_AUTH_ID_TOKEN="invalid"; \
     /etc/rc.d/init.d/panda-mcp restart'
   python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http
   # Should see authentication error
   ```

### Troubleshooting Checklist

When MCP is not working, check in this order:

- [ ] Container is running: `sudo docker ps | grep panda-mcp`
- [ ] MCP process alive: `sudo docker exec panda-mcp pgrep -af mcp_main`
- [ ] Port is listening: `sudo docker exec panda-mcp netstat -tlnp | grep 25888`
- [ ] Config files valid: Check JSON syntax
- [ ] Environment variables set: `sudo docker exec panda-mcp env | grep PANDA`
- [ ] Token not expired: Check `.token` file
- [ ] API endpoint correct: `PANDA_API_URL` ends with `/api/v1`
- [ ] Can reach API directly: Test with curl
- [ ] MCP client has token: Check `.token` file exists
- [ ] Logs show errors: Check stderr log

---

## Summary

### What Was Fixed

1. **mcp_main.py**: Changed module import path from URL-derived to hardcoded `api.v1`
2. **recreate_docker_bnl.sh**: Updated `PANDA_API_URL` from `/server/panda/api/v1` to `/api/v1`
3. **mcp_utils.py**: Added debug logging to trace authentication flow
4. **mcp_test_client.py**: Added automatic token loading and proper header configuration

### Key Learnings

1. **Module Paths Matter**: Python import paths must match actual package structure
2. **API Endpoints Vary**: Different PanDA servers may have different URL structures
3. **Authentication Flow**: OIDC token must flow through: Client → MCP → API
4. **Debugging Approach**: Isolate each layer (network → process → import → auth → API)
5. **FastMCP Protocol**: Plain HTTP won't work; must use MCP protocol format

### Success Criteria

When everything works correctly:
```bash
$ python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http
Loaded token from .token file
Connecting to PanDA Server at http://localhost:25888/mcp with transport streamable-http
Using OIDC authentication with VO: EIC
Client connected

Available tools:
- is_alive - [description]
- get_user_attributes - [description]

Testing is_alive:
Result: [Content(type='text', text='{"success": true}')]
```

---

## Quick Reference Commands

```bash
# Recreate container with fixes
./recreate_docker_bnl.sh

# Check everything is running
./diagnose_mcp_docker.sh

# Test MCP client
source panda-mcp/bin/activate
python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http

# Watch logs live
sudo docker exec panda-mcp tail -f /var/log/panda/panda_mcp_stderr.log

# Quick restart
sudo docker restart panda-mcp && sleep 5

# Enter container for debugging
sudo docker exec -it panda-mcp bash
```

# Build aid2e in docker container
```bash
sudo docker build -f Dockerfile.aid2e \
    --build-arg AID2E_INSTALL_EXTRAS=all \
    -t aid2e-mcp:latest .

# Check if the build and installation succeeded
sudo docker run -f --rm aid2e-mcp:latest aid2e --help
```


# SWF PanDAMon MCP Integration and Testing Plan

## Purpose

Plan the integration of the PanDAMon/PanDA MCP server into the streaming workflow testbed project and define the testing needed to make the integration reliable.

This plan assumes two related MCP surfaces:

- The standalone PanDA MCP server from `ghcr.io/pandawms/panda-server:latest`, run as a Docker sidecar and connected to the BNL SDCC PanDA server.
- The streaming workflow monitor MCP server, which already has PanDA Monitor-style tools such as `panda_list_jobs`, `panda_diagnose_jobs`, `panda_list_tasks`, `panda_error_summary`, `panda_get_activity`, and `panda_study_job`.

The first milestone is to integrate and test the standalone PanDA MCP server as a stable external tool source. Later milestones can either keep it as a separate MCP endpoint or compose/proxy it into the SWF monitor MCP surface.

## Current Local Context

Relevant local files:

- `recreate_docker_bnl.sh`: recreates a Docker `panda-mcp` container pointing at BNL SDCC.
- `DEBUGGING_GUIDE.md`: captures working MCP/Docker debugging procedures and known failures.
- `panda_server_config.json`: configures PanDA MCP transport and endpoint-list file.
- `panda_mcp_endpoints.json`: current local endpoint allowlist for baseline tools.
- `panda_mcp_endpoints_ssl.json`: larger endpoint allowlist for job, task, and user query tools.
- `mcp_test_client.py`: FastMCP client used for direct tool-level validation.
- `mcp_agent.py`: natural-language agent that discovers and calls MCP tools through FastMCP transports.
- `mcp_main.py` and `mcp_utils.py`: locally patched PanDA MCP files copied into the Docker image by `recreate_docker_bnl.sh`.

Important local findings from `DEBUGGING_GUIDE.md`:

- The working independent MCP port is `25888`.
- The working API base for BNL SDCC is `http://pandaserver01.sdcc.bnl.gov:25080/api/v1`, not `/server/panda/api/v1`.
- FastMCP requires an MCP client. Plain HTTP probes against `/mcp` can return `406 Not Acceptable` and still indicate that the route exists.
- OIDC credentials must flow through `Authorization: Bearer <ID token>` and `Origin: <VO>`.
- Prior startup failures were caused by invalid JSON config, wrong module-path derivation, and endpoint names that did not exist in the installed PanDA package.

## Current Verified Status, 2026-06-09

The standalone Docker PanDA MCP path is now working locally against BNL SDCC.

Verified evidence from the latest local run:

- `./recreate_docker_bnl.sh` successfully stops/removes the old container and creates a new `panda-mcp` container.
- The script extracts `id_token` from local `.token` and injects it into the container as `PANDA_AUTH_ID_TOKEN`.
- The container is created from `ghcr.io/pandawms/panda-server:latest` with BNL SDCC API and monitor environment variables.
- `panda_server_config.json` and `panda_mcp_endpoints.json` are copied into the expected container paths.
- Locally patched `mcp_main.py` and `mcp_utils.py` are copied into the image to support OIDC auth behavior.
- After restart, the MCP server is reachable at `http://localhost:25888/mcp/`.
- `mcp_agent.py --server docker` works after activating the local Python environment with `source panda-mcp/bin/activate`.
- The agent connects through FastMCP, lists 5 tools, and successfully answers the prompt "Is the PanDA-Server alive?" by calling `is_alive`.

Currently exposed tools:

- `is_alive`
- `get_user_attributes`
- `get_status`
- `get_description`
- `get_available_event_range_count`

Known local client requirement:

- Running `python mcp_agent.py --server docker` from the base environment fails with `ModuleNotFoundError: No module named 'fastmcp'`.
- Running from the project virtual environment works:

```bash
source panda-mcp/bin/activate
python mcp_agent.py --server docker
```

Current conclusion:

- The remaining integration work is no longer basic Docker/MCP reachability.
- The next milestone should focus on reproducible preflight/smoke checks, expanded read-only endpoint coverage, and deciding how this MCP endpoint will be consumed by the streaming workflow testbed.

## Requirements

### Runtime Requirements

- Docker with permission to run `sudo docker`.
- Network reachability from the container to BNL SDCC PanDA:
  - `pandaserver01.sdcc.bnl.gov:25080`
  - `pandaserver01.sdcc.bnl.gov:25443`
  - `pandamon01.sdcc.bnl.gov` when monitor URLs are needed by clients.
- Local port `25888` available for the independent MCP server.
- Python 3.11+ for local MCP clients and the LLM agent.
- Python client dependencies:
  - `fastmcp`
  - `requests`
  - LLM backend dependencies already used by this repo.

### Authentication Requirements

- A valid OIDC token source, currently represented by local `.token`.
- `PANDA_AUTH=oidc`.
- `PANDA_AUTH_ID_TOKEN=<id_token>` set in the container for server-side calls and/or passed by the client as an MCP request header.
- `PANDA_AUTH_VO=EIC` unless another VO is explicitly required.
- MCP client headers:
  - `Authorization: Bearer <id_token>`
  - `Origin: EIC`

The `.token` file must remain local and must not be committed.

### PanDA MCP Configuration Requirements

The Docker container needs:

- `PANDA_API_URL=http://pandaserver01.sdcc.bnl.gov:25080/api/v1`
- `PANDA_API_URL_SSL=https://pandaserver01.sdcc.bnl.gov:25443/api/v1`
- `PANDA_URL=https://pandaserver01.sdcc.bnl.gov:25443/server/panda`
- `PANDA_URL_SSL=https://pandaserver01.sdcc.bnl.gov:25443/server/panda`
- `PANDACACHE_URL=https://pandaserver01.sdcc.bnl.gov:25443/server/panda`
- `PANDAMON_URL=https://pandamon01.sdcc.bnl.gov`
- `PANDA_USE_NATIVE_HTTPLIB=1`
- `PANDA_BEHIND_REAL_LB=1`

The MCP config file should be valid JSON and should point to the endpoint allowlist:

```json
{
  "mcp": {
    "transport": "http",
    "endpoint_list_file": "/opt/panda/etc/panda/panda_mcp_endpoints.json"
  }
}
```

The initial endpoint allowlist should stay small and read-oriented:

```json
{
  "system": ["is_alive", "get_user_attributes"],
  "job": ["get_status", "get_description"],
  "event": ["get_available_event_range_count"],
  "statistics": ["job_stats_by_cloud", "active_job_stats_by_site"]
}
```

After baseline tests pass, expand toward:

```json
{
  "system": ["get_user_attributes"],
  "job": ["get_status", "query_jobs", "get_job_metadata", "get_panda_ids"],
  "task": ["get_task_status", "query_tasks", "get_taskparams", "get_job_ids"],
  "user": ["get_user_jobs"]
}
```

Each endpoint must be verified against the installed `pandaserver.api.v1.<module>_api` module before it is exposed.

## SWF PanDAMon MCP Integration Requirements Assessment

This assessment focuses on integrating the SWF PanDAMon MCP server, which is broader than the standalone `panda-mcp` sidecar. The SWF monitor MCP server is expected to expose SWF system/workflow tools, AI memory tools, PanDA Monitor tools, and PCS tools from a Django/FastMCP service. Its PanDA Monitor tools are expected to include `panda_list_jobs`, `panda_diagnose_jobs`, `panda_list_tasks`, `panda_error_summary`, `panda_get_activity`, and `panda_study_job`.

Current count: 12 requirements total; 4 fulfilled, 4 partially fulfilled, and 4 missing.

| Requirement | Status | Evidence / Gap |
|---|---:|---|
| FastMCP-compatible client | Fulfilled | `mcp_agent.py` and `mcp_test_client.py` already use `StreamableHttpTransport` / `SSETransport`. |
| Working local MCP/PanDA client environment | Fulfilled | Docker PanDA MCP works after `source panda-mcp/bin/activate`; the agent connects and calls `is_alive`. |
| OIDC/header support | Fulfilled for PanDA sidecar | `mcp_agent.py` sends `Authorization`, `X-PANDAAUTH-TOKEN`, and `Origin` headers. |
| LLM-backed natural-language tool use | Fulfilled | `mcp_agent.py` discovers tools and calls them through Ollama or vLLM. |
| Configurable MCP endpoint | Partial | Host, port, and protocol are configurable, but the MCP path is hardcoded to `/mcp/`. SWF FastMCP may use a different mounted path, such as `/` behind its MCP ASGI app. |
| Multi-server or sidecar composition model | Partial | This plan identifies sidecar vs composition, but the current agent connects to one MCP endpoint at a time. |
| Docker deployment pattern | Partial | Standalone `panda-mcp` Docker deployment exists; SWF monitor Docker deployment is not implemented in this repo. |
| Smoke/debug procedures | Partial | `DEBUGGING_GUIDE.md` provides strong manual diagnostics, but no automated SWF MCP smoke test exists yet. |
| SWF monitor server code present locally | Missing | This repo does not contain the SWF monitor Django app, `monitor_app.mcp`, or `swf_monitor_project/mcp_asgi.py`. |
| SWF workflow/testbed data backend | Missing | SWF requires monitor state from workflow messages, ActiveMQ consumption, and DB-backed monitor models. That backend is not present locally. |
| PanDAMon `panda_*` tool surface | Missing | Current exposed tools are standalone PanDA MCP tools, not SWF tools such as `panda_list_jobs`, `panda_diagnose_jobs`, `panda_error_summary`, and `panda_study_job`. |
| Permission model for SWF write/control tools | Missing | SWF includes potentially mutating tools such as workflow start/stop, message sending, agent control, and PCS status changes. The current framework has no tool permission policy. |

Conclusion:

- The current repository is ready as a client-side MCP/LLM integration base.
- The standalone PanDA MCP sidecar is working and can remain useful as an isolated PanDA API tool source.
- The repository is not yet a full SWF PanDAMon MCP integration because the SWF monitor service, data backend, `panda_*` tool surface, and permissions model are not present locally.
- The next practical integration test is to make the client accept an arbitrary MCP URL/path, connect it to a running SWF monitor MCP endpoint, call `swf_list_available_tools`, then call one read-only PanDAMon tool.

## Deployment Plan

### Phase 1: Stabilize the Standalone Docker MCP Server

Use `recreate_docker_bnl.sh` as the deployment baseline.

Planned improvements:

- Validate `.token` exists and contains `id_token` before container creation.
- Validate `panda_server_config.json` with `python3 -m json.tool`.
- Validate `panda_mcp_endpoints.json` with `python3 -m json.tool`.
- Before copying endpoint config into the container, check that each configured endpoint exists in the installed PanDA API module.
- Keep the current local patches to `mcp_main.py` and `mcp_utils.py` as an interim step.
- Track the upstream version or commit of `ghcr.io/pandawms/panda-server:latest` used during successful validation.

Acceptance criteria:

- Confirmed: `panda-mcp` container starts through `recreate_docker_bnl.sh`.
- Confirmed: port `25888` is published to the host and the MCP URL is `http://localhost:25888/mcp/`.
- Confirmed: the FastMCP client path can list tools through `mcp_agent.py --server docker`.
- Confirmed: the agent can call `is_alive`.
- Still to automate: process, port, config, and log checks should be captured in a smoke-test script.

### Phase 2: Integrate with the Local Agent

Use `mcp_agent.py --server docker` as the primary local agent integration.

Planned work:

- Confirm `mcp_agent.py` sends the expected headers for both tool listing and tool calls.
- Confirm the default URL resolves to `http://localhost:25888/mcp/` for Docker mode.
- Add a short integration runbook to the README or keep this document as the source of truth.
- Keep a strict split between MCP transport tests and LLM reasoning tests.

Acceptance criteria:

- Confirmed: `mcp_agent.py --server docker` discovers 5 exposed tools.
- Confirmed: the agent can answer a health-check prompt by calling `is_alive`.
- Still to verify: `mcp_test_client.py` and `mcp_agent.py` should be compared against the same tool list in one repeatable smoke run.
- Still to verify: the agent can answer at least one job/task query after the endpoint allowlist is expanded.

### Phase 3: Decide Sidecar vs SWF Monitor Composition

There are two viable integration models.

Option A: Sidecar MCP endpoint

- Keep PanDA MCP as `http://localhost:25888/mcp/`.
- Configure agents to connect to both SWF monitor MCP and PanDA MCP.
- Lowest implementation risk.
- Best for initial debugging because Docker, PanDA API, and SWF monitor failures stay isolated.

Option B: SWF monitor composition/proxy

- Expose PanDA MCP tools through the SWF monitor MCP server or a local MCP gateway.
- Better user experience if agents should see one unified SWF/PanDAMon tool surface.
- Higher implementation risk because auth, headers, route paths, and tool-name collisions must be handled explicitly.

Recommended path:

1. Use Option A for the first stable integration.
2. Add a compatibility layer only after sidecar tests are repeatable.
3. If composing, prefix remote tools with `panda_` or `pandamcp_` to avoid collisions with existing SWF monitor tools.

### Phase 4: Productionize the Container

The current script is good for local development but should evolve before shared use.

Target improvements:

- Build a small derived Docker image instead of copying patched Python files after container creation.
- Pin the base image by digest or known version instead of relying on `latest`.
- Mount config files read-only where practical.
- Add a health check that uses an MCP client or a purpose-built smoke script, not a plain `curl /mcp` request.
- Write logs to predictable locations and document `stdout`, `stderr`, PID, and service status checks.
- Avoid storing long-lived OIDC tokens in image layers or committed files.

## Testing Plan

### 1. Static Configuration Tests

Run before creating or restarting the container:

```bash
python3 -m json.tool panda_server_config.json
python3 -m json.tool panda_mcp_endpoints.json
python3 -m py_compile mcp_agent.py mcp_test_client.py mcp_main.py mcp_utils.py
```

Expected result:

- JSON validates.
- Python files compile.
- No credentials are printed.

### 2. Container Lifecycle Tests

Run after `./recreate_docker_bnl.sh`:

```bash
sudo docker ps --filter "name=panda-mcp"
sudo docker logs --tail 50 panda-mcp
sudo docker exec panda-mcp pgrep -af mcp_main
sudo docker exec panda-mcp cat /var/log/panda/panda_mcp.pid
sudo docker exec panda-mcp env | grep PANDA
sudo docker exec panda-mcp netstat -tlnp | grep 25888
```

Expected result:

- Container is running.
- `mcp_main.py` is active.
- Port `25888` is listening.
- Required `PANDA_*` variables are present.
- Logs do not show import errors, JSON errors, or missing endpoint errors.

### 3. PanDA API Connectivity Tests

Run inside or from the container where credentials are available:

```bash
curl -H "Authorization: Bearer $PANDA_AUTH_ID_TOKEN" \
     -H "Origin: $PANDA_AUTH_VO" \
     http://pandaserver01.sdcc.bnl.gov:25080/api/v1/system/is_alive
```

Expected result:

- HTTP 200 for valid token/VO.
- No `/server/panda/api/v1` path is used for REST API calls.

### 4. MCP Protocol Tests

Use the FastMCP client, not plain `curl`:

```bash
python mcp_test_client.py --tool is_alive --host localhost --port 25888 --use_http
```

For tools with arguments:

```bash
python mcp_test_client.py \
  --tool get_status \
  --host localhost \
  --port 25888 \
  --use_http \
  --kv job_ids=<known_panda_id>
```

Expected result:

- Client connects.
- Tool listing works.
- `is_alive` returns success.
- Argumented tools return structured results or a clear PanDA-side validation error.

### 5. Agent Integration Tests

Run the local agent against the Docker MCP endpoint:

```bash
source panda-mcp/bin/activate
python mcp_agent.py --server docker
```

Prompts to test:

- "List the available PanDA tools."
- "Is the PanDA server alive?"
- "Check the status of PanDA job `<known_panda_id>`."
- "Show recent jobs for my user." after `user.get_user_jobs` is enabled.

Expected result:

- The agent lists tools without hallucinating unavailable tools.
- The agent emits exact MCP tool names and exact parameter names.
- The tool result is surfaced in the final answer.
- Authentication failures are reported as auth failures, not hidden as generic LLM failures.

### 6. Negative Tests

Run these intentionally during validation:

- Missing `.token` file.
- Invalid JSON in `panda_server_config.json`.
- Endpoint name that does not exist in the installed `pandaserver.api.v1` module.
- Wrong API URL using `/server/panda/api/v1`.
- Expired or invalid OIDC token.
- Wrong VO in `Origin`.
- Port `25888` already occupied.
- Client using HTTPS against plain HTTP Docker MCP.
- Plain `curl` to `/mcp`, confirming that `406 Not Acceptable` is understood as a protocol mismatch rather than a service failure.

Expected result:

- Each failure has a clear diagnosis path.
- Startup failures show in Docker or PanDA MCP logs.
- Auth failures return PanDA-side authorization errors.
- Transport mismatches are reproducible and documented.

### 7. Regression Test Checklist

Use this checklist before declaring the integration working:

- [ ] `panda_server_config.json` validates.
- [ ] `panda_mcp_endpoints.json` validates.
- [x] `.token` exists locally and is not committed.
- [x] `panda-mcp` container is created by `recreate_docker_bnl.sh`.
- [ ] `panda-mcp` container is running, verified by `sudo docker ps`.
- [ ] `mcp_main.py` process is running, verified by `pgrep`.
- [ ] Port `25888` is listening in the container, verified by `netstat` or `ss`.
- [x] Host can reach the MCP server through `http://localhost:25888/mcp/` using a FastMCP client.
- [ ] `mcp_test_client.py` lists tools.
- [x] `mcp_agent.py --server docker` lists tools from the activated `panda-mcp` virtual environment.
- [x] `is_alive` succeeds through the natural-language agent.
- [ ] At least one job query succeeds with a known PanDA ID.
- [ ] At least one task query succeeds if task endpoints are enabled.
- [ ] Logs are checked after each test run.

## Observability and Debugging Procedure

Debug in this order:

1. Container state: `sudo docker ps -a --filter "name=panda-mcp"`.
2. Startup logs: `sudo docker logs --tail 100 panda-mcp`.
3. MCP process: `sudo docker exec panda-mcp pgrep -af mcp_main`.
4. Port state: `sudo docker exec panda-mcp netstat -tlnp | grep 25888`.
5. Config files inside container:
   - `/opt/panda/etc/panda/panda_mcp_endpoints.json`
   - `/opt/panda/etc/panda/config_json/panda_server_config.json`
6. PanDA MCP logs:
   - `/var/log/panda/panda_mcp_stdout.log`
   - `/var/log/panda/panda_mcp_stderr.log`
7. Direct PanDA API connectivity.
8. FastMCP client tool-listing.
9. FastMCP client tool-call.
10. LLM agent behavior.

Do not start with the LLM agent when debugging. First prove the MCP server and tool call work without an LLM.

## Risks and Mitigations

- Base image drift from `latest`: pin the Docker image after the first successful validation.
- Local patches copied into the container: replace with a derived image or upstreamed patch.
- Token leakage: never print full tokens, never commit `.token`, and prefer short-lived credentials.
- Tool drift: validate the endpoint allowlist against installed API modules.
- Transport confusion: document that Docker mode is HTTP streamable MCP at `http://localhost:25888/mcp`.
- Auth confusion: require both `Authorization` and `Origin` headers for authenticated calls.
- Tool-name collisions with SWF monitor MCP: prefix composed tools if a unified MCP surface is built.

## Open Questions

- Should the final deployment remain as a separate PanDA MCP sidecar, or should tools be composed into the SWF monitor MCP server?
- Which PanDA APIs are required for the first production workflow diagnostics use case?
- Should write operations ever be exposed through this integration, or should the first release remain read-only?
- What VO values beyond `EIC` need to be supported?
- Should the project maintain a derived Docker image for BNL SDCC integration?
- What is the canonical source for valid test PanDA IDs and task IDs?

## Near-Term Implementation Tasks

1. Add a smoke-test script that runs container checks and `mcp_test_client.py --tool is_alive`.
2. Add a preflight script that validates config JSON, token presence, endpoint/module availability, Docker availability, and port availability.
3. Update `recreate_docker_bnl.sh` to call preflight checks before removing or recreating the container.
4. Add a small integration-test script for one known job ID and one known task ID.
5. Document the chosen endpoint allowlist for the first milestone.
6. Decide whether to promote `panda_mcp_endpoints_ssl.json` or keep it as an expansion candidate.
7. Pin the Docker image version or digest used for the validated environment.
8. Decide how the streaming workflow testbed will consume PanDA MCP: direct sidecar endpoint first, then optional composition into the SWF monitor MCP surface.

## References

- PanDA MCP documentation: https://panda-wms.readthedocs.io/en/latest/advanced/mcp.html
- PanDA server repository: https://github.com/PanDAWMS/panda-server
- SWF monitor MCP integration document: https://github.com/wguanicedew/swf-monitor/blob/main/docs/MCP.md
- SWF monitor MCP tool registration: https://github.com/wguanicedew/swf-monitor/blob/main/src/monitor_app/mcp/__init__.py
- Local debugging guide: `DEBUGGING_GUIDE.md`


## Extracted PanDAMon Docker Checkpoint, 2026-06-09

This checkpoint reflects the current direction: `./swf-monitor` is reference code only. The project now extracts the PanDAMon MCP tool surface into a small standalone Docker service instead of deploying the full SWF monitor Django application.

### Current Implementation Artifacts

Created or updated local files:

- `instruction-for-pandamon.md`: extraction and Docker deployment instructions.
- `Dockerfile.pandamon`: Docker build recipe for the extracted service.
- `extracted/pandamon_server/pandamon_service/`: extracted service package.
- `extracted/pandamon_server/pandamon_service/app.py`: creates the FastMCP server.
- `extracted/pandamon_server/pandamon_service/asgi.py`: starts Django, registers tools, and exposes the ASGI app.
- `extracted/pandamon_server/pandamon_service/settings.py`: minimal Django settings for database access.
- `extracted/pandamon_server/pandamon_service/tools.py`: adapted copy of `swf-monitor/src/monitor_app/mcp/pandamon.py`.
- `extracted/pandamon_server/pandamon_service/queries.py`: copied from `swf-monitor/src/monitor_app/panda/queries.py`.
- `extracted/pandamon_server/pandamon_service/constants.py`: copied from `swf-monitor/src/monitor_app/panda/constants.py`.
- `extracted/pandamon_server/pandamon_service/sql.py`: copied from `swf-monitor/src/monitor_app/panda/sql.py`.
- `test-docker-swf-pandamon-mcp.sh`: local run script created by the user to remove and run the container.

The extracted service runs separately from the existing PanDA MCP sidecar:

```text
panda-mcp          -> http://localhost:25888/mcp/
swf-pandamon-mcp  -> http://localhost:25889/mcp/
```

### Tests Completed

1. Python syntax check for the extracted service:

```bash
python3 -m py_compile extracted/pandamon_server/pandamon_service/*.py
```

Result: passed.

2. Docker image build:

```bash
sudo docker build -f Dockerfile.pandamon -t swf-pandamon-mcp:local .
```

Result: passed. Image built successfully as `swf-pandamon-mcp:local`.

3. Container startup through local run script:

```bash
./test-docker-swf-pandamon-mcp.sh
```

Result: container started as `swf-pandamon-mcp`, mapped `25889:25889`, and became healthy.

Observed logs:

```text
INFO:     Started server process [7]
INFO:     Waiting for application startup.
StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:25889
```

4. Docker health check:

```bash
sudo docker ps --filter name=swf-pandamon-mcp
```

Result: container status became `healthy`.

5. MCP client connection and tool discovery:

```bash
python mcp_test_client.py --host localhost --port 25889 --use_http --tool panda_get_activity
```

Result: client connected to `http://localhost:25889/mcp`; FastMCP tool discovery worked.

Discovered tools included:

- `panda_list_jobs`
- `panda_diagnose_jobs`
- `panda_list_tasks`
- `panda_error_summary`
- `panda_get_activity`
- `panda_list_queues`
- `panda_get_queue`
- `panda_resource_usage`
- `panda_study_job`
- `panda_harvester_workers`

6. MCP tool-call path:

```bash
python mcp_test_client.py --host localhost --port 25889 --use_http --tool panda_error_summary --kv days=1 --kv limit=5
```

Result: tool execution reached the query layer, so MCP routing and `@mcp.tool()` registration are functional.

### Failures Found

#### Failure 1: Empty PanDA DB Environment Variables

Initial container environment showed:

```text
PANDA_DB_HOST=<EMPTY>
PANDA_DB_PORT=<EMPTY>
PANDA_DB_NAME=<EMPTY>
PANDA_DB_USER=<EMPTY>
PANDA_DB_SSLMODE=require
MCP_PORT=25889
PANDA_DB_PASSWORD=<EMPTY>
```

Tool call error:

```text
settings.DATABASES is improperly configured. Please supply the NAME or OPTIONS['service'] value.
```

Cause:

- The run script passed host shell variables into Docker.
- Undefined host variables became empty container variables.
- The original extracted `settings.py` used `os.environ[...]`, so empty values erased defaults.

Fix applied:

- Updated `extracted/pandamon_server/pandamon_service/settings.py` to treat empty strings as unset and reuse SWF monitor defaults where available:

```text
PANDA_DB_HOST=pandadb01.sdcc.bnl.gov
PANDA_DB_PORT=5432
PANDA_DB_NAME=panda_db
PANDA_DB_USER=panda
PANDA_DB_SSLMODE=require
```

Remaining requirement:

- `PANDA_DB_PASSWORD` must still be provided by the user/environment.

#### Failure 2: Default PanDA DB Hostname Does Not Resolve

After applying defaults, tool calls reached PostgreSQL hostname resolution and failed with:

```text
could not translate host name "pandadb01.sdcc.bnl.gov" to address: Name or service not known
```

Host checks showed:

```bash
getent hosts pandadb01.sdcc.bnl.gov
getent ahostsv4 pandadb01.sdcc.bnl.gov
```

Result: no output.

A known SDCC host did resolve:

```bash
getent hosts pandaserver01.sdcc.bnl.gov
# 2620:12f:f001:1::10 pandaserver01.sdcc.bnl.gov
```

Cause:

- `pandadb01.sdcc.bnl.gov` is not resolvable from the current host/network.
- This is not a Docker DNS issue because host DNS fails too.
- The hostname is only the default from `swf-monitor/src/swf_monitor_project/settings.py`; it may be a placeholder, internal-only name, or stale deployment default.

Current blocker:

- Need the real PanDA production database endpoint and credentials used by the deployed SWF monitor environment.

### Possible Causes and Solutions

| Symptom | Likely Cause | Solution |
|---|---|---|
| `settings.DATABASES is improperly configured` | Empty `PANDA_DB_NAME` or other DB env vars passed into Docker | Fixed in extracted settings by treating empty env vars as unset. Rebuild image after settings changes. |
| `could not translate host name pandadb01.sdcc.bnl.gov` | Default DB hostname does not resolve from this network | Obtain actual DB hostname or IP from SWF production environment or SDCC admin. Override `PANDA_DB_HOST`. |
| Host resolves DB but container does not | Docker DNS/network issue | Try `--network host` for debugging, or configure Docker DNS. Not the current observed issue. |
| DB TCP connection times out | Firewall/network ACL blocks access | Verify network/VPN/SDCC access and DB port reachability. |
| PostgreSQL auth failure | Wrong `PANDA_DB_USER` or `PANDA_DB_PASSWORD` | Use correct read-only DB credentials. |
| Permission denied on `doma_panda` tables | DB user lacks required read privileges | Grant/select read access to `doma_panda.jobsactive4`, `jobsarchived4`, `jedi_tasks`, `filestable4`, `schedconfig_json`, and harvester tables used by `study_job`. |
| `askpanda_atlas` import error | Optional tools/path not installed | Defer `panda_harvester_workers` and optional log-analysis paths, or add the required package later. |

### Next Actions

1. Obtain the real PanDA DB endpoint and credentials.
2. Export at least:

```bash
export PANDA_DB_HOST=<real-db-host-or-ip>
export PANDA_DB_NAME=panda_db
export PANDA_DB_USER=panda
export PANDA_DB_PASSWORD=<real-password>
export PANDA_DB_PORT=5432
export PANDA_DB_SSLMODE=require
```

3. Re-run:

```bash
./test-docker-swf-pandamon-mcp.sh
```

4. Verify resolved settings inside the container without printing the password:

```bash
sudo docker exec swf-pandamon-mcp python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','pandamon_service.settings')
import django
django.setup()
from django.conf import settings
db = settings.DATABASES['panda']
print('HOST=', db['HOST'])
print('PORT=', db['PORT'])
print('NAME=', db['NAME'])
print('USER=', db['USER'])
print('PASSWORD=', '<SET>' if db['PASSWORD'] else '<EMPTY>')
print('SSLMODE=', db['OPTIONS'].get('sslmode'))
"
```

5. Run database smoke test:

```bash
sudo docker exec swf-pandamon-mcp python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','pandamon_service.settings')
import django
django.setup()
from django.db import connections
connections['panda'].cursor()
print('db ok')
"
```

6. Retry MCP tools:

```bash
python mcp_test_client.py --host localhost --port 25889 --use_http --tool panda_get_activity
python mcp_test_client.py --host localhost --port 25889 --use_http --tool panda_list_tasks --kv days=1 --kv limit=5
python mcp_test_client.py --host localhost --port 25889 --use_http --tool panda_error_summary --kv days=1 --kv limit=5
```

### Current Status

- Extracted PanDAMon MCP service exists and builds.
- Docker container starts and is healthy.
- FastMCP transport and tool discovery work.
- Tool execution reaches the database query layer.
- The active blocker is the unresolved default PanDA DB hostname and missing real DB credentials.

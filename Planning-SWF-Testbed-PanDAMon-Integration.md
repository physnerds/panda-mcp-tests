# SWF Testbed PanDAMon MCP Integration Plan

## Recommendation

Use the already deployed SWF Monitor MCP endpoint as the primary PanDAMon
service for this project:

```text
https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/
```

The AID2E project should act as an authenticated remote MCP client. It should
not duplicate the PanDAMon server or connect directly to the PanDA database for
normal operation.

Keep the existing local extracted PanDAMon Docker work only as an optional
development fallback.

## Security Requirement

The bearer token shared in the email/conversation must be revoked and replaced
because it has been exposed in plaintext. The replacement token must be stored
only in the environment:

```bash
export SWF_MONITOR_MCP_TOKEN='<replacement-token>'
```

Do not commit the token, place it in example files, or pass it as a command-line
argument.

## Integration Boundary

Create a separate client implementation instead of modifying `mcp_agent.py`.
The new client will:

1. Connect using the complete reverse-proxy URL.
2. Send `Authorization: Bearer <token>`.
3. Discover tools through streamable HTTP.
4. Expose only the approved `panda_*` tools to the LLM.
5. Enforce the same allowlist before every tool call.
6. Reuse the existing `BaseAgent` and LLM provider abstractions.

The SWF endpoint does not require the PanDA-specific `Origin` or
`X-PANDAAUTH-TOKEN` headers used by the existing local PanDA MCP integration.

## Approved Tool Set

The initial exact allowlist is:

- `panda_get_activity`
- `panda_list_jobs`
- `panda_diagnose_jobs`
- `panda_list_tasks`
- `panda_error_summary`
- `panda_study_job`
- `panda_list_queues`
- `panda_get_queue`
- `panda_resource_usage`
- `panda_harvester_workers`

An exact allowlist is preferred over a prefix-only check. The remote endpoint
also exposes testbed and production tools, and newly added tools must not become
automatically callable by the AID2E agent.

## Files

- `swf_testbed_agent.py`: standalone LLM-driven PanDAMon MCP client.
- `swf_testbed_mcp_client.py`: direct tool discovery and invocation client.
- Existing `mcp_agent.py` and `mcp_test_client.py`: unchanged.

## Validation Sequence

Run from a machine that can reach SDCC:

```bash
export SWF_MONITOR_MCP_TOKEN='<replacement-token>'
```

List all server tools:

```bash
python swf_testbed_mcp_client.py --list-tools
```

List only the approved PanDAMon tools:

```bash
python swf_testbed_mcp_client.py --list-tools --allowed-only
```

Run the lowest-risk activity query:

```bash
python swf_testbed_mcp_client.py --tool panda_get_activity
```

Start the natural-language agent:

```bash
python swf_testbed_agent.py
```

Success criteria:

1. TLS and MCP initialization succeed.
2. The expected ten `panda_*` tools are discovered.
3. Non-allowlisted tools cannot be called through the agent.
4. `panda_get_activity` returns data or a clear server-side error.
5. No token value appears in logs, source files, or process arguments.

## Network Scope

The endpoint is expected to work directly from SDCC machines. Access from
outside BNL requires a separately managed tunnel or gateway and is outside the
initial integration scope.


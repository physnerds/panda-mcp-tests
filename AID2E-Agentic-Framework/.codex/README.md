# Codex Configuration

Codex reads one configuration file:

```text
.codex/config.toml
```

Codex does not currently expose a native TOML import/include setting in the
documented configuration reference, so this repo keeps MCP server definitions in
separate fragments and renders the single file Codex expects.

Edit these source files:

- `.codex/config.base.toml`
- `.codex/mcp_servers/openviking.toml`
- `.codex/mcp_servers/swf-testbed.toml`

Then regenerate:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python .codex/render_config.py
```

Restart Codex after regenerating so `/mcp` reflects the new server list.

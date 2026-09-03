# AGENTS.md

## Mission

This OpenViking MCP server test bed should be developed with eventual integration into `~/Documents/BNL-AiD2E/mcp-server/AID2E-Agentic-Framework` in mind.

Act as an expert MCP agentic-framework engineer. Bring strong context-engineering, prompt-engineering, RAG, vector database, and filesystem knowledge, but apply that expertise through the architecture already documented in AID2E-Agentic-Framework. The long-term goal is not to create an isolated agent loop here. The goal is to make OpenViking a clean MCP knowledge/resource layer that AID2E agents, Codex, Claude, or other MCP clients can discover, call, audit, and compose.

## Source Of Truth

Use these AID2E framework documents as the primary integration references:

- `../AID2E-Agentic-Framework/README.md`: framework responsibilities, refactoring direction, proposed structure.
- `../AID2E-Agentic-Framework/MULTI_AGENT_GUIDE.md`: BaseAgent design, LLM providers, multi-agent routing, testing patterns.
- `../AID2E-Agentic-Framework/agent/BaseAgent.py`: concrete FastMCP client flow, tool discovery, prompt construction, JSON tool-call parsing, result normalization, token usage tracking.
- `../AID2E-Agentic-Framework/agent/tool_description.md`: compact prompt template and exact JSON tool-call contract.
- `../AID2E-Agentic-Framework/agent/tool_instructions/*.md`: local routing, parameter, and presentation guidance for individual tools.
- `../AID2E-Agentic-Framework/Instructions.md`: remote MCP, token, SSL certificate, and SSH tunnel operational pattern.

When these documents conflict with generic agent advice, follow the AID2E documents.

## Python Environment

Use the project Python interpreter at:

```bash
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/panda-mcp/bin/python
```

Do not assume the system `python3` environment has the OpenViking or AID2E dependencies installed. Run OpenViking tests, package introspection, and local MCP server checks with the project interpreter unless a task explicitly requires a different environment.

## AID2E Architecture Alignment

AID2E is moving from a custom all-in-one agent framework toward a cleaner MCP-provider architecture.

Old responsibility model:

- Choose the LLM.
- Plan the task.
- Decide which MCP server or tool to call.
- Execute local and remote tools.
- Retry failures.
- Store observations.
- Summarize results.
- Decide the final answer.

Target responsibility model:

- Expose clean MCP tools.
- Enforce authentication and safety.
- Wrap local and remote services.
- Provide reusable workflow instructions.
- Log and audit tool calls.
- Optionally expose local or remote LLMs as services/tools.

For OpenViking, prefer building reliable MCP resources and tools over building another independent orchestration layer. Codex, Claude, and AID2E agents can already provide much of the agent loop if the MCP surface is clear enough.

## OpenViking Role In AID2E

Treat OpenViking as the knowledge filesystem, context-history layer, and observation sink for AID2E monitoring workflows. The intended integration shape is:

```text
                    AID2E Monitoring Agent
                              |
              +---------------+----------------+
              |               |                |
              v               v                v
         AID2E MCP        PanDA MCP       OpenViking MCP
              |               |                |
              |               |                |
        optimization       job/log         context/history
          state            state                |
              |               |                |
              +----------+----+                |
                         |                     |
                         v                     |
                     observation               |
                         |                     |
                         +-------------> OpenViking
                                            |
                                   +--------+--------+
                                   v                 v
                               Resource           Memory
                               evidence           learned
```

In this model, the AID2E Monitoring Agent coordinates three MCP surfaces:

- AID2E MCP provides optimization state and experiment/workflow state.
- PanDA MCP provides job state, log state, queues, errors, and operational telemetry.
- OpenViking MCP provides prior context, history, documentation, and memory, then stores new observations produced by the monitoring workflow.

Expected OpenViking capabilities:

- `find(query=...)`: semantic search over indexed knowledge.
- `ls(uri=...)`: resource and directory discovery.
- `read(uri=...)`: exact resource grounding.
- `abstract(uri=...)`: fast L0 orientation.
- `overview(uri=...)`: broader L1 summary.
- `add_resource(path)`: ingestion of filesystem content into OpenViking.

OpenViking should support AID2E agents that need documentation lookup, log knowledge, workflow rules, prior analyses, experiment runbooks, tool instructions, reusable domain context, and learned memory from previous observations.

## Integration Contract

Design OpenViking integration so an AID2E agent can use it like any other MCP-backed capability.

Required behavior:

- Discover resources before assuming paths exist.
- Search semantically with `find`, then ground answers by reading exact resources with `read`.
- Preserve resource URIs in results so downstream agents can cite provenance.
- Distinguish resource evidence from learned memory. Evidence should point to stable documents, logs, schemas, or workflow rules; memory should capture observations, summaries, decisions, and lessons learned from prior monitoring runs.
- Store new monitoring observations back into OpenViking with enough metadata to recover provenance: source MCP server, tool name, arguments, timestamp, related job/task/optimization identifiers, and confidence or status.
- Return structured errors for missing resources, auth failures, invalid URIs, empty indexes, and backend failures.
- Keep OpenViking-specific prompt guidance outside hardcoded application logic where practical.
- Make output predictable enough for `BaseAgent.normalize_tool_result()` and downstream formatting.

Do not make downstream agents parse human prose when structured JSON can be returned.

## BaseAgent Compatibility

AID2E `BaseAgent` expects this flow:

1. Build a FastMCP transport using SSE or Streamable HTTP.
2. Discover tools with `client.list_tools()`.
3. Format tool descriptions and input schemas into a compact tool prompt.
4. Ask the LLM for exactly one JSON object when a tool is needed: `{"tool": "tool_name", "arguments": {"param_name": value}}`.
5. Validate tool names against discovered tools.
6. Execute with `client.call_tool(tool_name, arguments)`.
7. Normalize `structuredContent` or JSON text content into Python data.
8. Format successful results for the user.
9. Return structured errors instead of throwing opaque failures.

When adding OpenViking tools or examples, make sure they work naturally with that flow.

## Tool Description Rules

Every OpenViking MCP tool should have a clear description and schema.

Tool descriptions must include:

- What the tool does.
- When to use it.
- Required and optional parameters with exact names.
- Resource URI expectations.
- Result shape.
- Common failure modes.

Use exact parameter names. If a schema says `uri`, do not document `path`. If a schema says `query`, do not document `search_text`.

For no-argument tools, make it clear that callers should pass an empty arguments object.

## Local Tool Instruction Pattern

AID2E uses local instruction files to improve routing and presentation. Follow that pattern for OpenViking tools when integrating.

Recommended future structure in AID2E:

```text
../AID2E-Agentic-Framework/
├── mcp_servers/
│   └── open-viking/
├── workflow_rules/
│   └── openviking_knowledge_retrieval.md
└── agent/
    └── tool_instructions/
        ├── openviking_find.md
        ├── openviking_ls.md
        ├── openviking_read.md
        ├── openviking_abstract.md
        ├── openviking_overview.md
        └── openviking_add_resource.md
```

Each instruction file should include:

- Use cases.
- Keywords for routing.
- Examples mapping user language to tool arguments.
- Common parameters.
- Output type.
- Presentation guidance.

Keep these files compact. They are routing aids, not full manuals.

## Context Engineering

Build context in layers:

1. Stable agent instructions and safety constraints.
2. The immediate user task and success criteria.
3. MCP tool schemas and local tool instructions.
4. Retrieved OpenViking resources with URI provenance.
5. Exact tool outputs from the current run.
6. Explicit assumptions and unresolved questions.

When an agent fails, inspect the context pipeline before editing prompts. Common causes are missing tool descriptions, stale vector indexes, vague resource names, oversized retrieved context, conflicting system instructions, or no exact `read` step after semantic search.

## Prompt Engineering

Prompts should be short and operational.

A good AID2E/OpenViking prompt tells the model:

- Which tools are available.
- The exact JSON format for tool calls.
- The exact parameter names.
- When to answer directly instead of calling a tool.
- How to handle absent evidence.
- How to present retrieved evidence.

Avoid long philosophical prompt blocks in runtime prompts. Keep philosophy and design rationale in documentation, then distill it into tool descriptions, workflow rules, and evaluation criteria.

## RAG And Vector Database Rules

Use RAG when answers depend on local, changing, large, or domain-specific knowledge. Do not use RAG for deterministic behavior that belongs in code or schemas.

Ingestion rules:

- Chunk by semantic boundaries such as headings, procedures, examples, and error records.
- Preserve source path, resource URI, timestamp, owner/domain, access scope, and document type as metadata.
- Store canonical `viking://` URIs alongside vector IDs.
- Deduplicate near-identical chunks before indexing.
- Keep secrets, tokens, private keys, and private certificates out of indexed content.
- Re-index after changing chunking, embeddings, metadata schema, or source files.

Retrieval rules:

- Use precise user intent first; expand queries only when recall is poor.
- Prefer hybrid retrieval where available: lexical constraints plus vector similarity.
- Filter by resource type, workflow, timestamp, domain, owner, and permission scope when metadata supports it.
- Retrieve enough candidates for recall, then rerank or filter before adding context.
- Treat top-k vector results as leads, not truth.

Generation rules:

- Ground substantive claims in exact resources, not only vector snippets.
- Cite or include resource URIs when presenting retrieved facts.
- Separate retrieved facts from model inference.
- Say when retrieval found no supporting evidence.
- Do not invent files, URIs, endpoints, tools, or schemas.

## OpenViking Filesystem Design

Treat `viking://` resources as a structured knowledge filesystem.

Recommended resource families:

- `viking://resources/docs/`: user and developer documentation.
- `viking://resources/workflow_rules/`: reusable AID2E workflow instructions.
- `viking://resources/tool_instructions/`: MCP tool routing and presentation notes.
- `viking://resources/examples/`: runnable examples and query/answer fixtures.
- `viking://resources/evaluations/`: expected retrieval and answer-quality cases.
- `viking://resources/logs/`: indexed log summaries or sanitized logs.
- `viking://resources/schemas/`: MCP schemas and structured data contracts.
- `viking://resources/evidence/`: stable source material used to ground monitoring answers.
- `viking://resources/memory/`: learned observations, historical summaries, decisions, and lessons from prior AID2E monitoring runs.

Prefer small, coherent files over giant mixed-purpose documents. Use stable, meaningful filenames. Align filesystem layout with the AID2E framework structure so migration is straightforward.

## Multi-Agent Usage

Use multiple agents only when specialization creates real value.

Good AID2E splits:

- MCP/server agent: discovers and executes tools.
- OpenViking knowledge agent: searches and reads knowledge resources.
- Log analysis agent: uses vector search over logs and known errors.
- Job or workflow agent: submits, monitors, and retries domain jobs.
- Review/evaluation agent: checks provenance, tests, and failure handling.

Every agent should have a bounded contract and a concrete artifact to return. Avoid designs where several agents restate the same reasoning without adding evidence or action.

## Security And Runtime

AID2E workflows often involve remote MCP servers, SSH tunnels, SSL certificates, and bearer tokens.

Follow these rules:

- Use environment variables for tokens and credentials.
- Never commit or index `.token`, `.token-swf`, bearer tokens, private keys, or private certificates.
- Redact tokens from logs and examples.
- Validate certificate paths before initializing remote clients.
- Distinguish auth failure, SSL failure, network failure, missing resource, invalid schema, and empty retrieval.
- Log tool calls and token usage when the framework supports it.

The SWF documentation shows the expected operational pattern: local laptop to SSH tunnel to SDCC to MCP server. Preserve that style when documenting OpenViking remote access.

## Testing And Evaluation

For OpenViking integration work, add tests or examples that cover:

- Tool discovery from the MCP server.
- `find` returning relevant resources for known queries.
- `ls` showing expected directories.
- `read` grounding a semantic search result.
- Empty search results.
- Invalid URI handling.
- Missing certificate or token behavior when remote access requires them.
- Structured error output.

For agent-level tests, follow AID2E patterns:

- Initialize the agent.
- Assert tools are discovered.
- Ask for available tools and verify a direct text response.
- Ask a retrieval question and verify the selected tool and grounded result.
- Check that output includes resource provenance when knowledge is retrieved.

## Working Style

Be pragmatic and evidence-driven. Before changing prompts, check whether the real fix belongs in MCP schemas, tool descriptions, local instruction files, retrieval metadata, resource layout, or tests.

When modifying this repository, keep the integration path visible: OpenViking should become a reliable AID2E knowledge and retrieval component, not an isolated experiment.

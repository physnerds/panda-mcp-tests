# Introduction

This is the workspace where we want to develop a more organized Agentic-Framework.  So far we have explored various tools and techniques needed to develop the framework. 

## What are the basic ingredients of the framework?

- Client layer (Claude, Codex, Custom)
- MCP servers layer (Either you build them or they are available)
- LLM service layer (Layer that can provide access to LLM remote, local, open, paid etc)


## What the framework needs to do?
The 4 main responsibilities of the framework are:

1. Route to approprialte model 
    - Local, remote, open, paid models
2. MCP tool discovery and execution
    - Framework need to discover available MCP servers that are hosted both remotely and locally
3. **Agent orchestration**
    - Planning, tool selection, retry, multi-step workflows etc
4. Security management, Runtime management
    - Managing tokens, ssh keys, authorization, observing and logging token usage etc

## Why do we want to move to using Claude or Codex?

We want to delegate some of the **agent orchestration** to these products. However this means that the framework needs to be refactored. 

The framework will change its task from :

```text
Your custom agent framework
├── chooses LLM
├── plans the task
├── decides which MCP server/tool to call
├── calls local/remote MCP servers
├── retries failures
├── stores observations
├── summarizes results
└── decides final answer
```

To:

```text
Your refactored system
├── exposes clean MCP tools
├── enforces auth and safety
├── wraps local/remote services
├── provides reusable workflow instructions
├── logs/audits tool calls
└── optionally delegates to local/remote open LLMs

```

This is because Codex or Claude as MCP client are capable of doing the following tasks by themselves or with small effort:

```text
Codex / Claude Desktop / other MCP client
├── uses its own agent loop
├── reads project instructions
├── discovers your MCP tools
├── calls your toolsr
```

This basically changes from responsibility of the framework from creating, managing and executing tools to providing MCP servers with tools and instructions. Local LLM provider itself becomes a MCP tool. See example [here](https://dev.to/0xkoji/run-codex-cli-with-local-llm-gemma4-with-llamacpp-on-wsl2-pee).


## Technical capabilities that are needed (and inherited from existing work)

1. The framework should be able to use local and remote MCP servers. 
2. The framework should be able to use LLM models available locally and remotely.
3. The framework should be able to use tokens and credentials for secured communication if needed.
4. For both local and remote MCP servers, the framework should provide information on each MCP tool. 
5. Framework should provide AGENTS.md or similar document that allows to recycle the workflow when performing tasks that require using multiple MCP tools, finalizing information etc. 
6. Framework should provide instruction on how to summarize the information (table, list, plot etc)


## Proposed structure

```text
AID2E-Agentic-Framework
├── mcp_servers/
│   ├── panda-idds/
│   ├── swf-agents/
│   ├── aid2e/
│   ├── git/
│   ├── logs/
│   ├── local_model/
│   ├── remote_model/
├── workflow_rules/
│   ├── panda_failure_debugging.md
│   ├── aid2e_submission.md
│   └── logging_rules.md
├── auth/
├── logging/
├── tests/
└── clients/ (For example .codex/ to save config.toml specific to AID2E-Framework)

```

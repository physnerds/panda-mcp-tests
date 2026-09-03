# openviking_add_resource

Use when the user asks to ingest a local file into OpenViking.

Keywords:
- add resource
- ingest
- index in OpenViking
- store in OpenViking
- add to knowledge base
- save memory

Examples:
- "add ./workflow_rules/openviking_knowledge_retrieval.md to OpenViking" -> {"path": "./workflow_rules/openviking_knowledge_retrieval.md"}
- "ingest ./logs/job-123-summary.md and wait" -> {"path": "./logs/job-123-summary.md", "wait": true}

Common parameters:
- path: required local filesystem path
- to: optional destination supported by OpenViking
- parent: optional parent resource URI supported by OpenViking
- wait: wait for ingestion completion
- timeout: optional timeout in seconds

Output type:
JSON object with ok, operation, arguments, and data containing the OpenViking ingestion response.

Presentation:
Report the resulting URI or ingestion identifier if returned. Never ingest secrets, tokens, private keys, private certificates, or unsanitized sensitive logs.

# openviking_find

Use when the user asks for AID2E/OpenViking knowledge, documentation, workflow rules, prior analyses, indexed memory, or "find/search/lookup in OpenViking".

Keywords:
- OpenViking
- viking
- knowledge base
- documentation
- memory
- prior context
- workflow rules
- semantic search

Examples:
- "find OpenViking docs about user authentication" -> {"query": "user authentication"}
- "search OpenViking for PanDA retry guidance" -> {"query": "PanDA retry guidance"}
- "look under workflow rules for failed job triage" -> {"query": "failed job triage", "target_uri": "viking://resources/workflow_rules/"}

Common parameters:
- query: required search text
- target_uri: optional viking:// subtree filter
- limit: maximum matches, default 10

Output type:
JSON object with ok, operation, arguments, and data containing OpenViking search results.

Presentation:
Show matching resource URIs and short evidence summaries. Follow up with openviking_read for exact grounding before making substantive claims.

# openviking_read

Use when the user asks to open, read, cite, inspect, or ground an answer in an exact OpenViking resource URI.

Keywords:
- read viking
- open resource
- exact resource
- cite
- source
- show content

Examples:
- "read viking://resources/docs/runbook.md" -> {"uri": "viking://resources/docs/runbook.md"}
- "show the first part of viking://resources/logs/job-123.md" -> {"uri": "viking://resources/logs/job-123.md", "limit": 4000}

Common parameters:
- uri: required exact viking:// resource URI
- offset: starting offset, default 0
- limit: maximum amount to read, default -1

Output type:
JSON object with ok, operation, arguments, and data containing resource text.

Presentation:
Cite the viking:// URI when summarizing content. If the content is long, summarize and mention the requested offset/limit.

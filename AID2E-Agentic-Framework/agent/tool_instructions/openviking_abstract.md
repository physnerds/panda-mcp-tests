# openviking_abstract

Use when the user asks for a quick summary or orientation for a known OpenViking resource URI.

Keywords:
- abstract
- quick summary
- L0
- orientation
- summarize resource

Examples:
- "abstract viking://resources/docs/runbook.md" -> {"uri": "viking://resources/docs/runbook.md"}

Common parameters:
- uri: required exact viking:// resource URI

Output type:
JSON object with ok, operation, arguments, and data containing the OpenViking L0 abstract.

Presentation:
Make clear that the response is an abstract. Use openviking_read for exact evidence if the user needs details.

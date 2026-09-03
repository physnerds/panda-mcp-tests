# openviking_overview

Use when the user asks for a broader OpenViking L1 overview of a known resource or subtree.

Keywords:
- overview
- L1
- broad summary
- summarize directory
- resource overview

Examples:
- "overview of viking://resources/workflow_rules/" -> {"uri": "viking://resources/workflow_rules/"}

Common parameters:
- uri: required viking:// resource or subtree URI

Output type:
JSON object with ok, operation, arguments, and data containing the OpenViking L1 overview.

Presentation:
Treat the result as a summary layer. Read exact resources before using it as evidence for operational decisions.

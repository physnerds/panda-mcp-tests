# openviking_ls

Use when the user asks what OpenViking resources, directories, files, or knowledge areas are available.

Keywords:
- list OpenViking
- show resources
- viking directory
- what is indexed
- browse knowledge base

Examples:
- "list OpenViking resources" -> {}
- "show resources recursively" -> {"uri": "viking://resources/", "recursive": true}
- "list workflow rules in OpenViking" -> {"uri": "viking://resources/workflow_rules/"}

Common parameters:
- uri: viking:// URI to list, default viking://resources/
- simple: simplified output if supported
- recursive: include descendants if supported

Output type:
JSON object with ok, operation, arguments, and data containing OpenViking listing entries.

Presentation:
Group directories and resources by URI. Do not assume a resource exists until it appears in the listing.

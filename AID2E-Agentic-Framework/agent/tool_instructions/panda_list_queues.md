# panda_list_queues

Use when the user asks for available PanDA queues, queue search, or queues by VO/site.

Common parameters:
- vo: virtual organization such as eic
- search: substring to match queue names or sites

Output type:
JSON object with a list of PanDA compute queues and queue summary fields.

Presentation:
Show queues as a table with queue name, site, status, resource type, and relevant summary fields.

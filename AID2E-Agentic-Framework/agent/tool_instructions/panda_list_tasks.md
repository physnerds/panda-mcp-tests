# panda_list_tasks

Use when the user asks for JEDI/PanDA tasks, task status, task counts, or task-level summaries.

Common parameters:
- status: task state such as failed, running, finished, done
- days: look back this many days
- user: production user name if supported by the server schema
- limit: maximum rows to return
- before_id: pagination cursor if returned

Output type:
JSON object with task summary counts, list of JEDI tasks, job-count aggregates per task, and pagination.

Presentation:
Show task summary counts first, then a compact task table.

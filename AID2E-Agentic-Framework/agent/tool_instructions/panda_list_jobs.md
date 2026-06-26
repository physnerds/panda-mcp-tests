# panda_list_jobs

Use when the user asks for a list of PanDA jobs by status, user, site, task, or recent time window. 
Do no use if the user is asking about a single job.

Common parameters:
- status: job state such as running, failed, finished, cancelled, activated
- days: look back this many days
- limit: maximum rows to return
- before_id: pagination cursor when next_before_id is returned
- user: production user name if supported by the server schema
- site: compute site if supported by the server schema

Output type:
JSON object with summary counts, total_in_window, jobs list, pagination fields, and applied filters.

Presentation:
Show summary counts first, then a compact jobs table. Do not print raw JSON unless the user asks for raw JSON.

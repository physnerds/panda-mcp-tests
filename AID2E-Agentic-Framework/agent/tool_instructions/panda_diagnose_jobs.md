# panda_diagnose_jobs

Use when the user asks why jobs failed, wants faulty jobs, pilot errors, executor errors, DDM errors, or failure diagnostics.

Common parameters:
- days: look back this many days
- site: compute site filter
- user: production user name if supported by the server schema
- limit: maximum rows to return
- before_id: pagination cursor if returned

Output type:
JSON object with failed/faulty job records, detailed error fields, and pagination.

Presentation:
Show error counts if available, then a table with pandaid, status, site, user, task, error source/code, and diagnostic text.

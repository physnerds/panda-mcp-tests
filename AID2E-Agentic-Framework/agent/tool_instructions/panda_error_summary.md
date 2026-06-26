# panda_error_summary

Use when the user asks for error summaries, top errors, failure patterns, common PanDA errors, or error counts over a time window.

Common parameters:
- days: look back this many days
- user: production user name if supported by the server schema
- site: compute site if supported by the server schema
- limit: maximum ranked error patterns to return

Output type:
JSON object with ranked error patterns, counts, affected users, affected sites, and task counts.

Presentation:
Prefer a ranked table of error pattern, count, users, sites, and affected tasks. Do not print raw JSON unless requested.

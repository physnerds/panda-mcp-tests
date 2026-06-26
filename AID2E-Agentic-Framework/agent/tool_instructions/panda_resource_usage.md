# panda_resource_usage

Use when the user asks for resource usage, core hours, site usage, user usage, or task usage.

Common parameters:
- days: look back this many days
- site: compute site filter, often supports SQL-like wildcards
- user: production user name if supported by the server schema

Output type:
JSON object with aggregate core-hour usage, usually broken down by site, user, or task.

Presentation:
Show totals first, then usage breakdown tables.

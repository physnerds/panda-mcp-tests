# panda_study_job

Use when the user asks for details about one specific PanDA job. If the user gives multiple PanDA job IDs, call this tool once per pandaid and summarize the results together.

Keywords:
- study job
- study the job
- job detail
- job details
- job summary
- job url
- monitor url
- panda monitor
- give me the url
- log url
- diagnose job
- inspect job
- job logs
- job errors
- job files
- status of job
- job status

Examples:
- "study job 958688" -> {"pandaid": 958688}
- "summary of panda jobs 958706" -> {"pandaid": 958706}
- "study the job #958688" -> {"pandaid": 958688}
- "give me the url of job 958688" -> {"pandaid": 958688}
- "give me the monitor url for this job 958688" -> {"pandaid": 958688}
- "summary of panda jobs 958706, 958782" -> call once with {"pandaid": 958706}, then once with {"pandaid": 958782}
- "study pandaids 958706 and 958782" -> call once with {"pandaid": 958706}, then once with {"pandaid": 958782}

Common parameters:
- pandaid: numeric PanDA job identifier

Output type:
JSON object with detailed single-job record, files, errors, log URLs, Harvester information, and parent task context.

Presentation:
Give a list of key : value 

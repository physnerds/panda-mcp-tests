# OpenViking And PanDA Integration Test Outline

## Purpose

Use OpenViking as the knowledge, evidence, and memory layer for AID2E
multi-step PanDA/iDDS workflow development. The integration test should run or
exercise a realistic AID2E PanDA workflow, collect structured PanDA evidence,
write sanitized local artifacts, ingest those artifacts into OpenViking, and
verify that future agents can find, read, and summarize them through MCP.

This test should cover two systems at once:

- AID2E PanDA/iDDS multi-step runner behavior.
- OpenViking MCP resource ingestion, semantic search, exact reads, abstracts,
  and overviews.

## Issue Source

GitHub issue:

```text
https://github.com/aid2e/AID2E-framework/issues/60
```

Issue title:

```text
Status of the multistep PanDA Runner
```

The issue asks for AID2E support for fan-out/fan-in multi-step PanDA/iDDS jobs
for optimization trials. The original problem is that a single-stage PanDA job
forces simulation/reconstruction and analysis to be bundled together, which
limits parallelism. The desired model is one logical optimization trial that
fans out into multiple simulation/reconstruction PanDA jobs, fans into one
analysis PanDA job, then returns objective results to the optimizer.

## Development Context

AID2E framework checkout:

```text
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/AID2E-framework
```

OpenViking MCP test bed:

```text
/home/amitbashyal/Documents/BNL-AiD2E/mcp-server/AID2E-Agentic-Framework/mcp_servers/open-viking
```

Relevant AID2E files and docs from the issue/local checkout:

- `src/aid2e/schedulers/PanDAiDDS/multistep.py`
- `src/aid2e/schedulers/PanDAiDDS/runner.py`
- `src/aid2e/utilities/runtime_builders.py`
- `examples/evaluators/dtlz2.py`
- `input-panda.yml`
- `input-panda-multistep.yml`
- `input-panda-multistep-datasets.yml`
- `PANDA-CLI-Implementations-Progress.md`
- `PANDA-Multi-Step-Issue-Note.md`

## Current Multi-Step PanDA Model

The supported payload shape is intentionally strict:

```yaml
payload:
  evaluator_type: "panda_multistep"
  steps:
    - name: "simreco"
      python_callable: "examples.evaluators.dtlz2:panda_multistep_simreco"
    - name: "ana"
      python_callable: "examples.evaluators.dtlz2:panda_multistep_ana"
      depends_on: "simreco"
```

Scheduler-epic-style `objective_funcs` and `deps` runtime payload support was
removed to keep AID2E payload management simpler and aligned with the current
CLI/config execution model.

The issue comments describe two useful execution modes:

- Single PanDA trial mode: run an entire optimization trial as one PanDA job.
- Multi-step PanDA trial mode: break one logical trial into coordinated PanDA
  works, such as `N` sim/reco jobs plus one analysis job.

The multi-step mode supports dependency maps such as:

- `one2one`: one upstream parent job feeds the corresponding downstream child
  job.
- `all2one`: multiple upstream parent jobs feed one downstream child job.

Dependency type controls what is passed between steps:

- `results`: parent job returns Python result values, usually a dictionary, and
  the scheduler hands those values to the child step.
- `datasets`: parent job writes output datasets, and downstream jobs consume
  those datasets through iDDS/PanDA/Rucio dependency plumbing.

## Dependency Clarifications From Issue 60

The issue discussion clarified that PanDA/iDDS dependencies are not the same as
adding a SLURM `afterok` dependency after each job submission. For multi-step
PanDA workflows, the dependency contract should be described in the workflow
payload so the scheduler/iDDS layer can submit and coordinate the related work.

Two dependency-management modes were clarified:

1. PanDA-managed dataset dependency: the parent task output dataset becomes the
   child task input dataset. PanDA can then manage the dependency and release
   child jobs when the parent dataset condition is satisfied.
2. Scheduler-managed dependency: the scheduler waits for a step to complete,
   collects outputs or result values, marks that step complete, and then
   triggers downstream ready steps.

For AID2E, the important open design surface is how outputs map between stages
and jobs, especially `one2one` and `all2one` handoff for dRICH-like workflows.

## Target Workflow Shape

The target dRICH-style optimization trial is:

```text
optimizer trial
  -> local launch/coordinator
  -> sim/reco PanDA job 1
  -> sim/reco PanDA job 2
  -> ...
  -> sim/reco PanDA job N
  -> analysis PanDA job
  -> local objective aggregation
  -> objective result returned to optimizer
```

For a two-child smoke test:

```text
initial launch job, local
  -> sim/reco job 1, PanDA
  -> sim/reco job 2, PanDA
  -> ana job, PanDA
  -> calculate objective, local
```

`input-panda-multistep-datasets.yml` is the intended real-PanDA smoke example
for dataset-backed handoff. The issue notes that dataset handoff still needs
ironing out, especially the parent-task to child-task contract.

## OpenViking Test Goal

The OpenViking integration test should preserve the operational evidence from
this PanDA workflow so future AID2E agents can answer questions such as:

- Which AID2E config was used?
- Which PanDA/iDDS jobs were created for a logical optimization trial?
- Which jobs were parents and which were children?
- Was the handoff `results` or `datasets`?
- Was the dependency map `one2one` or `all2one`?
- Which task/job IDs reached terminal states?
- Which failure modes appeared in PanDA, iDDS, Harvester, Rucio, or logs?
- Which OpenViking resources contain the run summary and exact evidence?

## Test Prerequisites

Start or confirm access to:

- PanDA/iDDS credentials and authorized PanDA user setup.
- AID2E framework checkout with the PanDA multi-step branch/features.
- PanDA MCP server or PanDA monitoring MCP tools.
- OpenViking backend on `https://aipanda106.cern.ch:443`.
- OpenViking MCP wrapper on `http://localhost:25901/mcp`.
- CERN SSL certificate environment for OpenViking.
- OpenViking API key file.

The issue comments note that PanDA access requires onboarding with Wen Guan and
adding the authorized username to `setup_panda.sh` through `PANDA_USERNAME`.

## Test Scenario

1. Start the OpenViking MCP server and confirm `openviking_*` tools are
   discoverable.
2. Start the PanDA MCP server and confirm PanDA task/job tools are discoverable.
3. In the AID2E framework checkout, load PanDA runtime environment and
   credentials.
4. Run a small multi-step smoke workflow, preferably:

   ```bash
   aid2e optimize input-panda-multistep-datasets.yml
   ```

   If dataset handoff is unstable, first run:

   ```bash
   aid2e optimize input-panda-multistep.yml
   ```

5. Capture one logical optimization trial identifier, iDDS request/workflow
   identifiers, PanDA task IDs, PanDA job IDs, step names, dependency map, and
   dependency type.
6. Query PanDA MCP for task/job evidence.
7. Write sanitized local evidence artifacts.
8. Ingest the artifacts with `openviking_add_resource`.
9. Verify that OpenViking can list, find, read, abstract, and overview the
   ingested resources.
10. Record a manifest mapping AID2E trial IDs, PanDA/iDDS IDs, local evidence
    files, and OpenViking resource URIs or ingestion identifiers.

## PanDA Evidence To Collect

Collect whichever fields are available:

- AID2E command, config path, git branch, and commit.
- Logical optimization trial ID or scheduler job ID.
- Payload `evaluator_type`, `steps`, `depends_on`, `dep_map`, and `dep_type`.
- iDDS request ID, workflow ID, work IDs, and internal IDs.
- PanDA task IDs and PanDA job IDs.
- Parent-child relationships, especially `parent_internal_id`.
- Task status and job status.
- Queue, site, cloud, campaign, user, timestamps, and terminal state.
- Output dataset names and input dataset names for dataset handoff.
- Result payload summaries for result handoff.
- Pilot log URLs or log metadata.
- Harvester worker information.
- Rucio dataset/rule/replica symptoms when dataset handoff fails.
- Structured error fields and diagnostic summaries for failed jobs.

Useful PanDA MCP tools include:

- `panda_list_tasks`
- `panda_list_jobs`
- `panda_study_job`
- `panda_diagnose_jobs`
- `panda_error_summary`
- `panda_harvester_workers`
- `panda_get_queue`

For single-job inspection, prefer `panda_study_job` because it can return the
job record, files, log URLs, Harvester data, parent task context, structured
errors, and diagnosis.

## OpenViking Evidence Layout

Create a deterministic local evidence directory:

```text
tmp/openviking-panda-evidence/<timestamp>-issue-60-<short-run-id>/
```

Suggested files:

- `run-summary.md`: high-level summary of command, config, status, and outcome.
- `aid2e-config.yml`: sanitized copy of the AID2E workflow config.
- `dependency-map.md`: human-readable explanation of steps, parents, children,
  `one2one`/`all2one`, and `results`/`datasets`.
- `panda-task-<taskid>.json`: selected task fields.
- `panda-job-<pandaid>.json`: raw or lightly normalized job detail.
- `panda-job-<pandaid>-summary.md`: human-readable job summary.
- `panda-datasets.md`: dataset names, parent/child handoff, and Rucio-relevant
  notes.
- `panda-logs.md`: log URLs, pilot log summary, and notable sanitized snippets.
- `openviking-ingestion-manifest.json`: local paths, target URIs, ingestion
  status, and returned OpenViking identifiers.

Do not ingest secrets, tokens, private keys, private certificates, bearer
tokens, full credential-bearing URLs, or unsanitized logs.

## Sanitization Rules

Before calling `openviking_add_resource`:

- Remove API keys, bearer tokens, passwords, certificates, private keys, and
  proxy contents.
- Redact local credential paths and user-private filesystem paths when not
  needed for diagnosis.
- Strip or redact signed URLs if they embed credentials.
- Keep job IDs, task IDs, request IDs, timestamps, status values, site names,
  queue names, dependency maps, error categories, and non-sensitive file names.
- Prefer compact summaries over full raw logs unless log content has been
  reviewed.

## OpenViking Verification

After ingestion, verify:

- `openviking_ls` shows the expected resource location when a target URI or
  parent URI was used.
- `openviking_find` can locate the run by issue number, run ID, task ID, job ID,
  dependency keyword, failure keyword, or config name.
- `openviking_read` returns exact ingested content for `run-summary.md` and one
  detailed evidence file.
- `openviking_abstract` returns a useful L0 abstract for at least one evidence
  file.
- `openviking_overview` returns a useful L1 overview for the run resource group.

Example verification queries:

```text
issue 60 multistep panda all2one dataset handoff
panda_multistep input-panda-multistep-datasets
parent_internal_id one2one all2one
PanDA dataset handoff Rucio failure
```

## Success Criteria

The combined test is successful when:

- AID2E can run or exercise a multi-step PanDA/iDDS workflow.
- The test records whether the workflow used `results` or `datasets` handoff.
- The test records whether the workflow used `one2one` or `all2one` mapping.
- PanDA MCP retrieves useful evidence for the resulting task and jobs.
- Sanitized evidence files are created deterministically.
- OpenViking ingests those files without errors.
- The ingested files can be found, read, abstracted, and overviewed through
  OpenViking.
- The manifest maps AID2E trial IDs and PanDA/iDDS IDs to OpenViking resource
  URIs or ingestion identifiers.

## Follow-Up Implementation Work

Potential implementation tasks:

- Add a helper that converts PanDA MCP responses into sanitized evidence files.
- Add a manifest writer for OpenViking ingestion results.
- Add an integration-test marker so this workflow is skipped unless PanDA and
  OpenViking credentials are configured.
- Add a stable resource URI convention under OpenViking, such as
  `viking://resources/evidence/aid2e/panda/issue-60/<run-id>/`.
- Add checks that detect dataset-handoff failures and preserve Rucio/iDDS/PanDA
  symptoms for later debugging.
- Clarify in AID2E docs whether stage/job/step terminology should converge, as
  issue 60 notes vocabulary drift between the paper and code.

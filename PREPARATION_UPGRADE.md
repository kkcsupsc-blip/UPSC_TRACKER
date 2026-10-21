# Preparation Upgrade

The tracker separates planned activity completion from assessment evidence.
Pipeline completion means the selected revision activities were marked done;
it does not establish mastery, retention, exam readiness, or a likely result.

## Architecture

- [app.py](app.py): Flask application, authentication, topic lifecycle, study logs, shared-capacity scheduling and timeline estimates, full-store JSON export/import, and local persistence.
- [preparation.py](preparation.py): preparation API blueprint, subject profiles, strategy and prerequisite validation, bounded resources, mapped syllabus coverage, assessment attempts, evidence summaries, training goals, and repair records.
- [static/js/preparation.js](static/js/preparation.js): opt-in Strategy & Evidence forms and views for strategies, attempts, goals, and repair resolution.
- [static/css/preparation.css](static/css/preparation.css): preparation view styling.
- [templates/index.html](templates/index.html): existing views and navigation, preparation entry point, asset includes, and current help guidance.
- [static/js/app.js](static/js/app.js): existing tracker views, activity actions, scheduling warnings, CA links, and pipeline finish labels. Internal names such as `masteryDate` remain for API compatibility; the displayed date is a pipeline forecast, not a mastery prediction.

## Start Locally

This is a Flask app, not a Streamlit app. From the repository root, with the
project's Python environment selected, install [requirements.txt](requirements.txt)
and run:

```powershell
python -m pip install -r requirements.txt
python app.py
```

The development server uses `http://127.0.0.1:5000`. A separate development
instance can use `python -m flask --app app run --port 5002` when another port
is needed. Do not start a second instance against the same JSON store: use an
isolated data copy for previews or tests. Neither command above was needed for
the text/template validation described below.

## Opt-In Strategy and Evidence

New strategy, source-mapping, prerequisite, assessment, goal, and repair workflows
are opt-in. Existing topics do not need a strategy profile or assessment record.
Leaving strategy scope unconfigured keeps the standard stage fallback. Scheduler
correctness fixes and the clarified labels are not optional exam modes.

- Standard scope has 11 activities for Both, or 9 for Prelims Only or Mains Only, before overrides. CA links are not a twelfth stage.
- Stage resolution uses explicit topic `activeStages`, then subject `defaultStages`, then the exam-type fallback with the configured standard/compact scope. Compact filters that fallback list; it does not replace explicit stage selections. Review the resolved topic plan for the actual count.
- Subject profiles describe practice outputs. Selecting a profile or setting an exam date does not automatically switch exam modes or build an exam-phase curriculum.
- Bound each foundation, spine, or depth resource by chapters or scope. Depth reading requires a named gap or question. Verify syllabus entries against the current official syllabus and map them to topics before interpreting coverage. Coverage measures mapped learning completion, not factual correctness, exhaustive coverage, or retention.
- No PDFs are imported automatically. The tracker does not extract a verified syllabus from documents, validate source facts, or evaluate answers automatically.
- Log actual study hours and completed activities. Elapsed days and planned allocations are not actual study logs or evidence of knowledge.
- Attach and review a topic's CA links before starting learning if useful; verify dates and factual claims yourself.

## Evidence and Repairs

MCQ, writing, recall, and subject-skill attempts remain separate from pipeline
completion. Timed unseen/mixed MCQs, sample size, delayed recall, and externally
evaluated writing inform the relevant evidence statuses. Self-assessed writing
is labeled separately; unreviewed writing is not an evaluated score. Diagnostic
or repeated MCQ sets remain diagnostic-only. Previously on-target evidence can
become stale; skill checks are recorded rather than converted to readiness scores.

Configurable training goals are personal practice targets, not official UPSC
cutoffs, pass marks, or guaranteed readiness. Missing evidence is not failure,
and an on-target result is not a promise about exam performance.

Tagged assessment errors create repair items. Their due dates are follow-up
reminders, not automatically reserved study time. Resolve an item with the
correction and retest outcome. The repair workflow does not provide fully
adaptive study scheduling or automatically allocate repair hours.

## Scheduling Limits

Existing and future work compete for shared daily capacity: learning, pending
revisions, cumulative sessions, and projected topic activities. Budgets,
durations, intervals, and prerequisites affect feasibility. The scheduler has a
finite search horizon and reports infeasibility instead of searching forever or
guaranteeing a date. Review warnings and revise unrealistic constraints.

The learning forecast window scales with remaining learning/activity hours,
weekly capacity, start staggering and existing calendar reservations, up to a
3,650-day safety limit. The former fixed 400-day learning cutoff does not truncate
larger courses. A planning-horizon limit is distinct from having no study hours.
Repeated warnings are grouped, and pipeline finish dates include the year.

Missing forecasts are shown as **Not scheduled**, not as evidence that the topic
does not exist. **Unallocated work** is work without an allocation in that plan;
the label does not imply automatic rollover to tomorrow or a reserved future slot.

## Data and Storage

Existing subjects, topics, revision records, study logs, links, cumulative
revisions, and subject cycles are preserved. There is no automatic PDF import,
data reset, or bulk content replacement required to use the new workflows.
Export a JSON backup before changing strategy settings or importing a snapshot.

Full-store JSON exports include the new collections when recorded:
`assessmentAttempts`, `repairItems`, and `activityHistory`, together with strategy
metadata and preparation settings. Older snapshots may omit these collections;
do not discard them when moving newer exports between installations.
Activity history provides audit records for relevant revision changes; it is not
a complete event-sourced history of every operation.

Local saves serialize to a temporary file in the store's directory, flush and
sync it, then atomically replace the JSON file. Request/load/save coordination
uses a **process-local lock**. This supports a **single worker/process only**;
atomic replacement is not cross-process locking or a multi-worker database.
Use a transactional shared store before deploying multiple workers or replicas.

Optional GitHub synchronization is asynchronous and **best effort**. Network,
authentication, API, or remote-write failures can leave it behind local state;
it is not a transactional backup or cross-worker synchronization mechanism.
Keep independent JSON backups and do not rely on GitHub sync alone.

## Validation

Run the isolated Python suites and frontend tests from the repository root:

```powershell
python -B -m unittest test_preparation test_strategy test_assessments test_scheduler_updates test_persistence
node --test test_preparation_ui.js
node --check static/js/app.js
node --check static/js/preparation.js
```

[test_preparation.py](test_preparation.py) extracts backend functions without
running application startup. [test_strategy.py](test_strategy.py) and
[test_assessments.py](test_assessments.py) use injected in-memory data;
[test_scheduler_updates.py](test_scheduler_updates.py) uses isolated scheduler
fixtures; [test_persistence.py](test_persistence.py) uses temporary stores and
mocked network access. [test_preparation_ui.js](test_preparation_ui.js) exercises
frontend helpers and fake-DOM workflows without the live tracker.

For template validation, render through a standalone Jinja `Environment` with
`FileSystemLoader("templates")`, `StrictUndefined`, HTML autoescaping, and a
dummy `cache_bust`. Check preserved view IDs, navigation targets, and preparation
script/style includes. Do not import the Flask application or request live data
routes just to render a template: startup or data loading can write real state.
# Preparation Upgrade

The tracker separates planned activity completion from assessment evidence.
Pipeline completion means the selected revision activities were marked done;
it does not establish mastery, retention, exam readiness, or a likely result.

## Architecture

- [app.py](app.py): Flask application, authentication, topic lifecycle, study logs, shared-plan integration for Today/Calendar/Timeline, full-store JSON export/import, and local persistence.
- [planner.py](planner.py): pure two-stream planning engine, daily pool budgets, session splitting, recall backlog guard, and stream/exam-scoped forecasts. Producing a plan does not start topics or write study logs.
- [planner_api.py](planner_api.py): `GET`/`PUT /api/planner`, validated configuration, canonical subject streams, explicit subject queues, and safe stream reassignment.
- [static/js/planner.js](static/js/planner.js): Settings planner controls, learning lanes, whole-stage completion and partial-session logging, budget labels, and milestone/recall-pressure views.
- [preparation.py](preparation.py): preparation API blueprint, subject profiles, strategy and prerequisite validation, bounded resources, mapped syllabus coverage, assessment attempts, evidence summaries, training goals, and repair records.
- [static/js/preparation.js](static/js/preparation.js): opt-in Strategy & Evidence forms and views for strategies, attempts, goals, and repair resolution.
- [static/css/preparation.css](static/css/preparation.css): preparation view styling.
- [templates/index.html](templates/index.html): existing views and navigation, preparation entry point, asset includes, and current help guidance.
- [static/js/app.js](static/js/app.js): existing tracker views, activity actions, scheduling warnings, CA links, and pipeline finish labels. Internal names such as `masteryDate` remain for API compatibility; the displayed date is a pipeline forecast, not a mastery prediction.

## Two-Stream Configuration

The implicit configuration is `mode: two-stream`, `attemptYear: 2028`, and
`phase: auto`; no data migration or saved planner block is required to apply
those defaults. Configure it in **Settings** and use **Save Planner**.

- Actual manual starts enforce **one active learner per stream**, allowing one GS and one Optional concurrently, not three topics or two GS topics. Completing initial learning releases that lane while its stages continue; forecasts do not make an actual manual start. Existing overfull legacy streams are warned about and advanced one at a time, without resetting progress.
- Explicit subject `studyStream` takes precedence. Otherwise the Sociology profiles `sociology1`/`sociology2`, or subject names containing Sociology/Optional, imply Optional; other subjects are GS. Topic exam type does not classify a stream.
- `gsSubjectOrder` and `optionalSubjectOrder` set explicit queues. Unlisted subjects use stable profile/name/ID fallback: Economy, Environment, Geography, History, Polity, Sociology I/II. Prerequisites and existing active learners still control eligibility.
- Integrated allocation defaults are **40% GS, 26.67% Optional, 15.56% recall, 11.11% practice, 6.66% current affairs**, approximately **18/12/7/5/3 hours at 45h/week**. Prelims defaults are **35/5/25/30/5** and Mains defaults **10/10/20/55/5** in that order. Each configurable row totals 100%, with positive GS/Optional learning shares.
- Auto selects Prelims within `prelimsFocusDays` (default **112**) before and including the user-entered Prelims date, Mains after Prelims through the user-entered Mains date (or onward if absent), and Integrated otherwise. An explicit phase overrides Auto. Attempt year alone supplies no exam dates; entered/example dates are not official UPSC schedule claims.

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
isolated data copy for previews or tests. Documentation validation requires no
application startup, server, or fixture server.

## Opt-In Strategy and Evidence

New strategy, source-mapping, prerequisite, assessment, goal, and repair workflows
are opt-in. Existing topics do not need a strategy profile or assessment record.
Leaving strategy scope unconfigured keeps the standard stage fallback. Scheduler
correctness fixes and the clarified labels are not optional exam modes.

- Standard scope has 11 activities for Both, or 9 for Prelims Only or Mains Only, before overrides. CA links are not a twelfth stage.
- Stage resolution uses explicit topic `activeStages`, then subject `defaultStages`, then the exam-type fallback with the configured standard/compact scope. Compact filters that fallback list; it does not replace explicit stage selections. Review the resolved topic plan for the actual count.
- Subject profiles describe practice outputs and can supply fallback stream classification. Planner phase/allocations are separate from topic exam type and active-stage selection; changing a profile or phase does not build a verified exam curriculum.
- Bound each foundation, spine, or depth resource by chapters or scope. Depth reading requires a named gap or question. Verify syllabus entries against the current official syllabus and map them to topics before interpreting coverage. Coverage measures mapped learning completion, not factual correctness, exhaustive coverage, or retention.
- No PDFs are imported automatically. The tracker does not extract a verified syllabus from documents, validate source facts, or evaluate answers automatically.
- Log actual study hours and completed activities. Elapsed days and planned allocations are not actual study logs or evidence of knowledge.
- Attach and review a topic's CA links before starting learning if useful; verify dates and factual claims yourself.

## Completion and Time Logs

Stages can span sessions on several days. **Mark Done** / the stage checkbox
completes the **whole activity**, not just the displayed session; the UI asks for
confirmation. **Session hours today** + **Log**, rendered by
`plannerStageControl`, records partial time without completing the activity.
Forecast-only stage controls are not actionable completion records.

`POST /api/study-logs` supports `stage` for an active activity on a learned
topic; omitted/`learning` identifies initial learning. Logs need positive hours
up to 24 and a valid non-future date; frontend stage controls log today. Stage
logs reduce stage work, not initial learning. Actual learning totals and the
`actual-logged` estimate replacement exclude all activity logs.

A stage marked done today without a same-day stage log reserves its remaining
estimated duration after earlier logged sessions as **Estimated time used**.
This is a capacity reservation, **not measured time or a fabricated log**.
Same-day actual stage time replaces the estimate. Budgets distinguish
**Logged**, **Estimated time used**, and **Remaining planned**.

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

Today, Calendar, and Timeline use the same engine and daily budget. Learning,
recall, practice, current affairs reserves, cumulative sessions, and subject
cycles compete for capacity; recorded time is not added on top of a full plan.
Stages split across sessions/days, and their forecast date is the final session.

- Recall/practice pools divide fairly between streams by their learning weights and outstanding demand, choosing earliest-due work within each stream. They do not drain GS file order before Optional. Idle learning quota can be borrowed for follow-ups.
- R3 depends on R1, not PYQ/ERA. R7 waits for MCQA when selected, otherwise MCQ or the next selected fallback; weekend consolidation is configurable and on by default. R30 follows recall, not MVA/MAINS. MVA and writing can begin after initial practice/analysis without waiting for the later recalls.
- `recallGuardDays` defaults to **7**; **0 disables it**. Recall later than that tolerance pauses **new forecast starts in the affected stream**, preserves existing active learning, and redirects idle learning quota to follow-ups/backlog recovery. It is a soft planning tolerance, **not an on-time recall guarantee**. Review `recallPressure[stream].maxDelayDays` and `guardedLearningDays[stream]`, shown as projected review delay and days with new learning deferred.
- Each stream has separate **First-pass coverage** and **Full activity pipeline** dates. Prelims-scoped finish includes only GS topics not marked Mains Only, excluding MVA/MAINS. Optional and other Mains-only work still consume the shared budget. Mains-scoped finish excludes Prelims-only topics. Exam deadlines subtract the configured buffer; late and unscheduled topics remain visible, not hidden to make dates fit.
- The fresh 211-topic dataset's **7.5h/topic** learning baseline remains uncalibrated. `provisionalTopics`/`provisionalCount` count unfinished topics whose `estimateSource` is neither `user-estimate` nor `actual-logged`; they do not count calibrated estimates as default-based. Dates can move as estimates and actual logs improve; coverage/pipeline dates do not guarantee readiness.

The simulation has a **3,650-day** safety horizon, not the former 400-day cutoff.
Zero study hours, impossible dependencies, unusable task pools, and fixed
reservations exceeding budget are real shortfalls to address. Missing dates
remain **Not scheduled**. **Unallocated work** is not a promise of automatic
rollover; inspect warnings and revise sustainable capacity, scope, or estimates.

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

Storage is unchanged by the planner documentation update. This work does not
push to GitHub, trigger synchronization, or redeploy the application.

## Validation

Run the isolated Python suites and frontend tests from the repository root:

```powershell
python -B -m unittest test_two_stream_planner test_planner_engine test_planner_api
python -B -m unittest test_preparation test_strategy test_assessments test_scheduler_updates test_persistence
node --test test_planner_ui.js test_timeline_ui.js test_preparation_ui.js
node --check static/js/app.js
node --check static/js/planner.js
node --check static/js/preparation.js
```

[test_two_stream_planner.py](test_two_stream_planner.py) checks stream/phase
contracts; [test_planner_engine.py](test_planner_engine.py) exercises shared
planning with isolated data; [test_planner_api.py](test_planner_api.py) checks
configuration and lifecycle/logging handlers without application startup.
[test_preparation.py](test_preparation.py) extracts backend functions without
running application startup. [test_strategy.py](test_strategy.py) and
[test_assessments.py](test_assessments.py) use injected in-memory data;
[test_scheduler_updates.py](test_scheduler_updates.py) uses isolated scheduler
fixtures; [test_persistence.py](test_persistence.py) uses temporary stores and
mocked network access. [test_preparation_ui.js](test_preparation_ui.js) exercises
frontend helpers and fake-DOM workflows without the live tracker.
[test_planner_ui.js](test_planner_ui.js) and
[test_timeline_ui.js](test_timeline_ui.js) cover planner controls and forecast
display; the planner suite includes a temporary local fixture server.
Do **not** run [test_optionc.py](test_optionc.py) for isolated validation: it
imports the live application. For this documentation-only work, use focused
Node checks of Markdown links/heading anchors; no suites, servers, or fixture
servers need to be started.

For template validation, render through a standalone Jinja `Environment` with
`FileSystemLoader("templates")`, `StrictUndefined`, HTML autoescaping, and a
dummy `cache_bust`. Check preserved view IDs, navigation targets, and preparation
script/style includes. Do not import the Flask application or request live data
routes just to render a template: startup or data loading can write real state.
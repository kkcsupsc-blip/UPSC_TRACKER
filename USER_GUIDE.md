# UPSC Preparation Tracker: Objectives, Stages, and User Guide

This is the practical handbook for the application as it currently works.

**The objective is to turn your subject strategies into bounded study, useful practice, error repair, and delayed revision. The application organises and records that work; it does not perform the studying or guarantee selection.**

## Contents

1. [What The Application Is Trying To Achieve](#1-what-the-application-is-trying-to-achieve)
2. [Your Starting Dataset](#2-your-starting-dataset)
3. [Open The Application](#3-open-the-application)
4. [Understand The Screens](#4-understand-the-screens)
5. [Understand Progress And Evidence](#5-understand-progress-and-evidence)
6. [The Topic Stages](#6-the-topic-stages)
7. [Standard, Compact, And Custom Activities](#7-standard-compact-and-custom-activities)
8. [First-Time Setup](#8-first-time-setup)
9. [Study One Topic: Step By Step](#9-study-one-topic-step-by-step)
10. [Record And Interpret Assessments](#10-record-and-interpret-assessments)
11. [Repair Errors And Integrate Current Affairs](#11-repair-errors-and-integrate-current-affairs)
12. [Cumulative And Subject-Level Revision](#12-cumulative-and-subject-level-revision)
13. [Read The Timeline Correctly](#13-read-the-timeline-correctly)
14. [Daily And Weekly Routine](#14-daily-and-weekly-routine)
15. [Backups, Resets, And Troubleshooting](#15-backups-resets-and-troubleshooting)

## 1. What The Application Is Trying To Achieve

| Objective | What The Application Provides | What You Must Supply |
| --- | --- | --- |
| Keep preparation bounded | Subjects, main topics, source scopes, and topic-linked coverage entries | A checked syllabus and sensible limits on reading |
| Make the next action visible | Learning status, Today's Plan, Calendar, and revision dates | Honest completion updates |
| Prevent unrealistic planning | Shared-capacity forecasts, activity durations, and scheduling warnings | Sustainable hours and calibrated topic estimates |
| Separate attendance from performance | Activity completion alongside independent assessment records | Actual scores, timing, and answer feedback |
| Convert errors into corrective work | Error categories, open repairs, due reminders, and resolution records | The correction and a genuine retest |
| Maintain knowledge beyond the first reading | Recall stages, cumulative revision, and subject cycles | Closed-book retrieval and mixed practice |
| Preserve preparation history | Saved progress, assessment history, activity audit records, and JSON export | Regular independent backups |

**Keep these four questions separate:**

- **Coverage:** Have I studied the required areas?
- **Activities:** Have I carried out the planned work?
- **Performance:** Can I answer accurately and within time?
- **Retention:** Can I still retrieve and apply it after a delay?

A completed activity does not automatically answer the other three questions.

## 2. Your Starting Dataset

The fresh dataset contains **211 main topics from seven subject PDFs**. Subtopics and coverage bullets were not imported as separate topics.

| Subject | Topics | Initial Exam Type |
| --- | ---: | --- |
| Economy | 37 | Both |
| Environment and Ecology | 21 | Both |
| Geography | 35 | Both |
| Modern History | 22 | Both |
| Polity and Governance | 57 | Both |
| Sociology Paper I | 18 | Mains Only |
| Sociology Paper II | 21 | Mains Only |
| **Total** | **211** | |

Topics retain their PDF code, layer, and page reference. Their initial learning estimates are **7.5 hours each**, with neutral **medium ROI**. These are editable planning defaults, not measured learning times or verified importance ratings.

The seeded coverage checklist mirrors the documents. It is **not independently verified against the official UPSC syllabus**. Subjects or papers without a source document were not invented; separately account for CSAT, Essay, Ethics, and any remaining syllabus areas.

Active progress lives in [data/tracker_data.json](data/tracker_data.json). The untouched clean import copy is [data/upsc_subjects_seed.json](data/upsc_subjects_seed.json). See the [dataset guide](data/SUBJECT_SEED_README.md) for rebuilding details.

## 3. Open The Application

1. Open **http://127.0.0.1:5002** if the tracker is already running there.
2. Sign in with your existing credentials.
3. Open **Subjects** to see the populated dataset. You do not need to import it again.

If the server is stopped, open a terminal in the repository folder and run:

```powershell
& .\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5002 --no-reload
```

Leave that terminal running while using the application. This is a **Flask** app, not a Streamlit app.

**Run only one tracker instance against the same data file.** If another tracker is running on port 5000 or 5002, use that instance or stop it before starting another. The current storage lock coordinates requests within one process, not across multiple servers.

## 4. Understand The Screens

| Screen | Primary Use |
| --- | --- |
| Dashboard | Review active learning, due work, overdue work, capacity, and a forecast summary |
| Subjects | Browse topics; start or finish learning; edit estimates, ROI, and exam type; open topic details |
| Strategy & Evidence | Configure subject sources, coverage, topic scope and prerequisites; record assessments; resolve repairs |
| Today's Plan | Carry out due work, log learning hours, and review due repair reminders |
| Calendar | Inspect scheduled activities on particular dates |
| Analytics | Review recorded activity progress and weekly study/revision reporting |
| Cumulative Rev | Arrange synthesis batches and subject-level revision cycles |
| Timeline | Inspect projected topic and subject completion dates under the current workload |
| Settings | Set available hours, dates, activity durations, intervals, notifications, and backup/import options |
| HTML Pages | Open supported uploaded HTML study pages; this is separate from assessment evidence |
| Help & Logic | Read the application's built-in explanation of its current rules |

## 5. Understand Progress And Evidence

### Topic Learning Status

| Status | What It Means | What It Does Not Mean |
| --- | --- | --- |
| Not Started | You have not started the topic's learning workflow | You cannot collect links or record a diagnostic |
| Learning | You explicitly started learning the topic | The app knows you studied merely because days passed |
| Completed / Revising | You marked the initial learning work complete; revision activities can now be tracked | Every revision is complete or your answers meet a target |
| Pipeline Complete | All activities in the topic's resolved active pipeline have been marked done | Permanent mastery or exam readiness |

### Three Different Actions

| Action | What It Records |
| --- | --- |
| **Log** in the New Learning Block | Actual hours spent on learning that topic |
| **Mark Done** for an activity | That you performed the selected activity |
| **Record attempt** in Strategy & Evidence | Counts, score, timing, feedback, and errors from an assessment |

These actions are separate. Recording a test does not automatically mark PYQ, MCQ, or MAINS done. Marking an activity done does not invent a test score.

## 6. The Topic Stages

### Do Not Confuse Layers, Sources, And Activities

| Term | Purpose | Where It Appears |
| --- | --- | --- |
| PDF topic layer | Organises related main topics in the source architecture | Topic source notes, codes, and PDF references |
| Reading tier | Determines which material to use: Foundation, Spine, or targeted Depth | Subject resources in Strategy & Evidence |
| Topic activity stage | Determines the follow-up work: R1, PYQ, ERA, and the other codes below | Topic Revision Timeline and Today's Plan |

During initial learning, follow the PDF's source protocol: use the required foundation, study the core spine, and add only justified depth. A document's Test tier is carried out through questions/writing and their assessment records; a current-affairs Feed tier can use CA Links. Neither is a separate extra learning status.

Learning happens first. The following codes describe the available follow-up activities.

**This table is an activity reference, not a rigid calendar sequence. Use the dates in the topic's Revision Timeline. Practice may share dates or move around capacity constraints.**

| Code | Objective | Work You Do | What The App Provides |
| --- | --- | --- | --- |
| **R1** | First retrieval after learning | Close the source, reconstruct the main ideas, then check omissions | A recall appointment, completion record, and Hard/Okay/Easy rating |
| **PYQ** | Understand how UPSC tests the topic | Attempt relevant previous-year questions and analyse the directive or statement logic | A practice appointment; assessment recording is available separately |
| **ERA** | Explain and correct PYQ errors | Identify why the answer or argument failed; return to the precise source gap | A separate analysis activity; tagged assessment errors can create repair tasks |
| **R3** | Retrieve again after a delay | Recall without notes and target weaknesses from the first pass | A second recall appointment and confidence rating |
| **MN** | Compress useful knowledge | Make concise micro notes from recurring gaps, traps, diagrams, or answer structures | A scheduled note-making activity; create the actual notes in your notebook or study tool |
| **MCQ** | Test application under time | Attempt an appropriately sized question set | A practice slot; the assessment form records counts, timing, and negative-marked scores |
| **MCQA** | Repair MCQ reasoning | Separate conceptual, factual, elimination, and timing errors | A separate analysis activity and assessment-linked repair workflow |
| **R7** | Consolidate and connect | Retrieve the topic, connect neighbouring topics, and test weak areas | A weekend consolidation appointment and confidence rating |
| **MVA** | Improve Mains content | Select useful arguments, evidence, studies, examples, or diagrams | A value-addition activity; the app does not generate or verify the content |
| **MAINS** | Produce a relevant answer within time | Write, obtain feedback, and rewrite where needed | A writing slot and separate writing-assessment records |
| **R30** | Recheck longer-delay retention | Perform another closed-book retrieval and repair remaining gaps | A final activity in the selected topic pipeline; further maintenance can still be needed |

### Timing Rules To Understand

- R1, R3, R7, and R30 are stage names, **not promises of exactly Day 1, 3, 7, and 30**.
- Built-in interval defaults are 1, 5, 14, and 35 days from learning completion. Your Settings may differ.
- Capacity, minimum gaps, selected stages, recorded completion dates, and confidence ratings affect actual dates.
- R7 is placed on a weekend. MN avoids sharing a date with that topic's practice clusters.
- PYQ + ERA and MCQ + MCQA are placed as practice clusters when both are pending. The combined duration must fit an available day.
- Hard/Okay/Easy ratings adjust relevant later recall offsets. MCQ scores and writing marks do **not** currently drive automatic rescheduling.
- A stage appointment is not a learning lock: completing a checkbox is not an assessment gate.

## 7. Standard, Compact, And Custom Activities

| Exam Type | Standard Count | Compact Count | Main Difference |
| --- | ---: | ---: | --- |
| Both | 11 | 8 | Compact removes MN, R7, and MVA from the fallback pipeline |
| Prelims Only | 9 | 7 | Standard already excludes MVA and MAINS; compact also removes MN and R7 |
| Mains Only | 9 | 6 | Standard already excludes MCQ and MCQA; compact removes MN, R7, and MVA |

Compact scope does not mean weaker learning is acceptable. It means fewer separately scheduled appointments. Still make necessary notes and perform essential consolidation within your study workflow.

**Stage selection precedence:**

1. A non-empty explicit topic selection in **Customize Active Stages**.
2. An existing subject-level `defaultStages` selection, if present in the stored data.
3. The topic's exam-type fallback, filtered by its Standard/Compact scope.

A topic's scope can inherit the subject strategy or override it. A profile such as Geography or Sociology describes the expected outputs; selecting that profile alone does not change the topic's exam type.

To return an explicitly customised topic to inheritance, clear its selections in **Customize Active Stages** and click **Save Stages**. An empty selection means inheritance, not a zero-activity pipeline. Check the resolved timeline afterwards.

## 8. First-Time Setup

### Step 1: Set Honest Capacity

1. Open **Settings**.
2. Set **Weekday Hours** and **Weekend Hours** to time you can actually sustain.
3. Review **Activity Durations (Hours)** and the revision intervals.
4. Save the settings.

An activity duration is a planning estimate, not a score or required study achievement. Recall and note-making durations scale with topic depth; practice/writing slots are time-boxed. Do not lower estimates merely to make the finish date look better.

### Step 2: Set Exam Dates Carefully

1. Enter your confirmed target Prelims and Mains dates.
2. Choose a realistic **Pre-Exam Buffer**.
3. Click **Save Exam Dates**.

Dates support countdowns, feasibility checks, and some subject-cycle suggestions. They do not automatically switch the whole application into an exam phase or universally prevent all work from falling inside the buffer or after the exam. Verify the actual Timeline.

### Step 3: Review One Subject Strategy

1. Open **Strategy & Evidence** and select a subject.
2. Confirm its **Profile** and **Activity pipeline**.
3. Review the source resources and keep the scope bounded to relevant chapters or sections.
4. Keep one core spine rather than reading every alternative listed in a PDF.
5. Give any **Depth** resource a specific gap or question that justifies opening it.
6. Review the topic-linked syllabus entries against the official syllabus.
7. Select **Syllabus verified against official syllabus** only after that comparison.
8. Click **Save strategy**.

The seeded checklist is topic-level. It is not necessary to enter all your subtopics into the tracker.

Use the profile outputs to choose appropriate evidence, not merely identical exercises for every subject:

| Subject Profile | Useful Output |
| --- | --- |
| Economy | Explain a mechanism and apply it to a policy or scenario |
| Polity and Governance | Distinguish rules/exceptions and compare institutions |
| Environment and Ecology | Explain an ecological mechanism and verify dated facts |
| Geography | Retrieve locations on a blank map and produce an annotated diagram |
| Modern History | Reconstruct chronology and explain cause/consequence |
| Sociology Paper I | Compare thinkers and construct an evaluated theoretical argument |
| Sociology Paper II | Apply an Indian study and connect it to Paper I theory |

### Step 4: Review Topic Scope And Dependencies

1. Under **Topic activity scope & prerequisites**, choose a topic.
2. Set **Activity scope** to Inherit, Standard, or Compact.
3. Select prerequisite topics only where their completed learning is genuinely necessary.
4. Click **Save topic strategy**.

The app rejects circular prerequisites. An unfinished prerequisite blocks starting dependent learning and affects its forecast. A related topic is different: it is a useful connection, not a prerequisite. Do not add every conceptual cross-link as a hard dependency.

## 9. Study One Topic: Step By Step

Use **Indian Monsoon Mechanism & Seasons of India** as an example.

1. **Find it:** Open Subjects, expand Geography, and select the topic.
2. **Check scope:** Review its source reference, relevant chapters, exam type, selected activities, and learning-hour estimate. Adjust the estimate through Edit if needed.
3. **Preview questions:** Inspect representative PYQs to understand what the topic must enable you to do. This is a recommended study method, not an automatically enforced stage.
4. **Start:** Click **Start** or **Start Learning**. The app allows at most three topics in Learning simultaneously. You do not have to fill all three slots.
5. **Learn:** Study the bounded core material. Explain the mechanism, retrieve key relations, and practise the relevant diagram or map outside the app.
6. **Log actual work:** Open Today's Plan, find the topic in **New Learning Block**, enter the learning hours actually spent, and click **Log**.
7. **Continue honestly:** Do not repeatedly log the same session. These learning logs reduce estimated remaining learning; they are not a generic log for every later revision session.
8. **Finish the first pass:** When the bounded learning work is complete, click **Done** in New Learning Block or **Mark as Completed** in topic details.
9. **Follow revision dates:** Reopen the topic's Revision Timeline and complete the due activities. Mark each done only after performing it.
10. **Record evidence:** Use Strategy & Evidence for timed questions, recall checks, subject-skill checks, or writing assessments. This is separate from the activity checkbox.
11. **Repair errors:** Tag relevant errors and complete the correction/retest workflow.
12. **Recheck later:** Use later recall, mixed tests, and cumulative revision rather than assuming the first successful session is permanent retention.

When learning is completed, recorded learning hours can replace the original estimate and influence later duration scaling. Accurate logs therefore improve subsequent planning.

Undo an activity if marked accidentally. This reopens an incomplete pipeline where applicable; it does not erase independent assessment evidence or undo work already performed in historical batches.

## 10. Record And Interpret Assessments

### Record An Attempt

1. Open **Strategy & Evidence** and choose the subject.
2. Find **Record attempt**.
3. Choose MCQ, Recall, Writing, or Subject skill.
4. Choose a specific topic, or **Subject / full paper** for a broader test.
5. Enter the actual date and minutes. Future assessment dates are rejected.
6. Choose the question-set type honestly: Diagnostic, Unseen, Mixed, or Repeated.
7. Complete the fields for that assessment type, add useful notes, and tag error categories.
8. Click **Record attempt**.

| Assessment | What To Enter | How To Interpret It |
| --- | --- | --- |
| MCQ | Correct, wrong, unattempted, minutes, marks per question, and wrong-answer penalty fraction | Accuracy and net marks are different measures; inspect both |
| Recall | Correct, wrong/missed, and unattempted retrieval items | Unretrieved items count against retrieval percentage |
| Writing | Maximum marks, awarded marks if evaluated, minutes, and Unreviewed/Self/External review | The app records your reported evaluation; it does not evaluate or authenticate an external review |
| Subject skill | A named skill plus correct, wrong/missed, and unattempted items | A record of the check, not an automatic readiness judgement |

For example, **15 correct and 5 wrong**, at **2 marks per question** and a **1/3 wrong-answer penalty**, gives **75% attempted-question accuracy** and **26.67 net marks**. Use the marking scheme of the actual paper; not every paper uses the same marks per question.

A subject/full-paper attempt remains in that subject's history. It does not automatically update every individual topic's evidence. Select a topic when the results genuinely support a topic-specific assessment.

### Understand Evidence Labels

| Label | Meaning |
| --- | --- |
| Not assessed | No applicable evidence, or writing has not been evaluated |
| Diagnostic only | The latest MCQ set is diagnostic or repeated, rather than an unseen/mixed readiness check |
| Small sample | Too few answered MCQs or recall items to meet the configured sample minimum |
| Early recall | Recall was recorded too soon after learning completion, or there is no learning completion date |
| Self-assessed | Writing was rated by you rather than recorded as externally evaluated |
| Needs practice | The recorded result does not meet the relevant current conditions or target |
| On target | The relevant latest assessment meets that dimension's configured training conditions |
| Stale | Previously on-target evidence is older than the configured freshness window |
| Recorded | A subject-skill check is saved without a readiness threshold |

The latest non-voided dated record of each assessment type drives that topic's displayed status. A later weak result can replace an earlier on-target status. Skill checks are grouped into one skill dimension; the display is not a separate mastery score for every named skill.

### Default Training Targets

| Setting | Built-In Default |
| --- | ---: |
| MCQ accuracy | 70% |
| Minimum MCQ questions answered | 20 |
| Recall retrieval | 70% |
| Minimum recall items | 5 |
| Delay after learning completion for recall | 7 days |
| Externally reviewed writing | 50% of maximum marks |
| Freshness window for on-target evidence | 21 days |

MCQs also need an Unseen/Mixed set and positive recorded time to become on target. Writing needs positive recorded time and External review. Your configured targets may differ from these defaults.

Change them under **Training targets (not selection cutoffs)** and click **Save training targets**. They are personal practice thresholds, **not UPSC cutoffs, CSAT qualification rules, or guarantees of selection**.

Use the history's void action for an invalid or wrongly entered attempt. Voiding retains the underlying record but excludes it from current evidence; its open repair tasks are cancelled. Do not void a genuine weak result just to improve the display.

## 11. Repair Errors And Integrate Current Affairs

### Resolve A Repair

1. Tag an assessment error: concept, fact, application, elimination, time, structure, evidence, map, or chronology.
2. Recording that attempt creates an open repair for each selected category.
3. New repairs receive a reminder date two days after recording. This is a follow-up convention, not a scientifically personalised interval.
4. Find the task under **Open repairs**. Due tasks are also flagged in Today's Plan through **Review Repairs**.
5. Revisit the exact gap, then attempt a fresh retrieval or application check.
6. Enter both **Correction** and **Retest outcome**.
7. Click **Resolve repair**. If the gap remains, leave the task open until it is meaningfully addressed.

Repair dates are reminders. Their hours are **not automatically reserved** in the scheduler, and resolving a repair does not automatically mark a topic stage complete. Allocate time deliberately. Optionally record the retest as another assessment to preserve its results.

### Add Current Affairs Before Starting A Topic

1. Open Subjects and click the topic's **CA Links** button.
2. Paste the URL, add an optional title, and click **Add**.
3. The topic stays Not Started. You do not need a free learning slot to save a link.
4. Later, open and review the article, then mark it read where appropriate.
5. Turn useful material into an argument, example, factual update, diagram, or question in your study work.

Current affairs is a continuous topic resource, **not a twelfth revision stage**. A read link is not evidence that its contents are accurate or retained.

## 12. Cumulative And Subject-Level Revision

Topic stages, cumulative batches, and subject cycles serve different purposes.

| Level | Objective | How To Use It |
| --- | --- | --- |
| Topic pipeline | Learn, practise, and revisit a bounded topic | Follow the topic's active activities |
| Cumulative batch | Integrate and retrieve multiple topics together | Use eligible completed-pipeline topics in synthesis batches and their sessions |
| Subject cycle | Consolidate and test a larger subject | Review suggested dates, schedule the block, and carry out its stated work |

Open **Cumulative Rev** to manage batches and subject cycles. Pipeline-complete topics can enter the pending pool for cumulative work; review the topics selected for a batch rather than treating it as an assessment result.

The subject cycles are **Consolidation, Active Recall, Targeted Repair, Rapid Fire, and Final Review**. Their R1-R5 names are a different system from a topic's R1/R3/R7/R30 activities.

Subject-cycle suggestions are planning aids, not verified evidence that the previous work has been completed. Confirm prerequisite preparation, available capacity, overlaps, and exam timing before accepting a block. The current exam-relative cycle logic is oriented around Prelims; separately plan optional/Mains-specific final revision.

## 13. Read The Timeline Correctly

1. Open **Timeline**.
2. Check the number of topics successfully forecast and the weekly study hours.
3. Review remaining learning and follow-up activity hours separately.
4. Read the full **Pipeline Finish** date, including its year.
5. Inspect subject dates, topic dates, and any grouped warnings.
6. Return to the underlying scope, estimates, or hours if the plan does not fit your preparation window.

The forecast uses current estimates, available hours, active activities, logged learning, existing reservations, and explicit prerequisites. It simulates new starts; **a forecasted start does not actually change a topic to Learning**.

Large courses are not cut off simply because they exceed 400 days. The learning horizon scales with workload up to a 3,650-day safety limit. Individual activity placement still has finite search limits and must fit the relevant daily capacity.

### What Warnings Mean

| Message Or Situation | Interpretation | Appropriate Response |
| --- | --- | --- |
| No study hours configured | There is no weekly learning capacity | Correct the available-hour settings |
| An activity exceeds daily budget capacity | A required task or combined practice cluster is larger than a usable day | Review realistic durations, scope, or capacity |
| No capacity within candidate days | The activity could not be placed within its finite search | Inspect reservations and restrictive activity rules |
| Forecast exceeds planning horizon | The simulated course still cannot finish within the safety window | Recheck total workload, dependencies, and available hours |
| Not scheduled | A reliable date was not produced | Read the warning; do not interpret this as zero days remaining |
| Unallocated work | Demand is not allocated in that displayed plan | Decide when to perform it; this does not promise automatic rollover tomorrow |
| Finish date is after your target exam | The current plan does not fit that target | Calibrate actual learning needs and essential activities rather than editing numbers to hide the mismatch |

Changing activity scope changes the forecast, not the amount of learning you truly need. The forecast is **not a marks predictor or a guarantee that an exam deadline will be met**.

## 14. Daily And Weekly Routine

### Every Study Day

- [ ] Review Today's Plan, overdue work, and due repair reminders.
- [ ] Choose a realistic amount of work within today's available time.
- [ ] Perform recall before rereading, where recall is the task.
- [ ] Complete the chosen learning/practice sessions outside the tracker.
- [ ] Log new-learning hours once, accurately.
- [ ] Mark only activities actually performed.
- [ ] Record meaningful assessment results and error categories.
- [ ] Save useful current affairs links without letting collection replace study.

### Once A Week

- [ ] Review Analytics and the weekly record of work actually logged.
- [ ] Inspect evidence quality and recurring errors, not just completed activities.
- [ ] Review open repairs and stale evidence in Strategy & Evidence.
- [ ] Recalibrate topic estimates from representative actual learning sessions.
- [ ] Check cumulative revision, subject cycles, and mixed practice.
- [ ] Review the Timeline against your real target dates.
- [ ] Export an independent JSON backup.

**Recommended discipline:** use the tracker briefly to decide and record work. Keep most preparation time for reading, retrieval, questions, writing, feedback, and correction.

## 15. Backups, Resets, And Troubleshooting

### Back Up And Restore

1. Open Settings and click **Export Data (JSON)** to download your current full tracker data.
2. Keep a dated copy outside the project folder.
3. Before importing any JSON, export the current data first.
4. Click **Import Data** and select a JSON file only when you intend to replace the installation's dataset.

The clean [seed JSON](data/upsc_subjects_seed.json) resets progress; it is not your latest study backup. Do not import it routinely.

The optional GitHub sync is best effort. Local saves and independent exports remain important. Do not assume remote sync is a transactional backup or multi-server coordination system.

### Common Questions

| Question | Answer |
| --- | --- |
| Why is there no learning work on my first day? | All seeded topics begin Not Started. Start a topic explicitly. |
| Why can I not start another topic? | Check the three-topic learning limit and unfinished explicit prerequisites. |
| Why did Compact not change this topic? | A non-empty topic or subject stage override takes precedence. Review the resolved active stages. |
| Why is writing still self-assessed? | You selected Self review. A checkbox or confidence rating is not external evaluation. |
| Why is my MCQ evidence diagnostic-only? | The latest set is Diagnostic or Repeated. Use an honest Unseen/Mixed assessment for that training check. |
| Why is recall early-recall? | Check learning completion and the configured delayed-recall threshold. |
| Why did a subject test not update every topic? | Subject/full-paper scope is not automatically attributed to individual topics. |
| Can I add links before starting? | Yes. CA Links is independent of learning status and available slots. |
| Does checking the syllabus verification box audit the syllabus? | No. It records your declaration that you performed that comparison. |
| Does the app check the PDF facts or score my answers? | No. Source verification and answer evaluation remain your responsibility. |
| Do I need to enter subtopics? | No. The installed dataset is main-topic level; manage finer detail in your study material. |

### Further Reference

- [Preparation Upgrade](PREPARATION_UPGRADE.md): architecture, storage limits, and technical behaviour.
- [Subject Seed Guide](data/SUBJECT_SEED_README.md): source counts, fresh-data defaults, and deliberate reset/rebuild commands.

**Working principle: study a bounded topic, retrieve it, apply it, examine the errors, repair them, and verify retention later. Use the application to keep those actions visible and honest.**
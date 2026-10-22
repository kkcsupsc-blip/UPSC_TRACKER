# Fresh Subject Dataset

The active [tracker_data.json](tracker_data.json) was rebuilt from the main numbered
topic headings in all seven subject PDFs. [upsc_subjects_seed.json](upsc_subjects_seed.json)
is the reusable clean import copy. The active file will change as you study; the seed
copy does not change unless you deliberately rebuild it.

| Subject | Main Topics | Exam Type |
| --- | ---: | --- |
| Economy | 37 | Prelims and Mains |
| Environment and Ecology | 21 | Prelims and Mains |
| Geography | 35 | Prelims and Mains |
| Modern History | 22 | Prelims and Mains |
| Polity and Governance | 57 | Prelims and Mains |
| Sociology Paper I | 18 | Mains |
| Sociology Paper II | 21 | Mains |
| **Total** | **211** | |

## Included

- Main topics only, in document order. Coverage bullets and subtopics were not imported.
- Original topic codes, layer names and PDF page references in topic notes and source metadata.
- Correct subject profiles, standard stage fallback, and bounded source recommendations. Legacy coverage mappings are retained as metadata, not shown as a syllabus editor.
- Every topic starts as `not-started`, with no start/completion dates or previous links.
- Study logs, completed activities, assessments, repairs, cumulative batches and subject cycles are empty.
- Learning duration and topic ROI/priority are **blank** until entered by the user; no 7.5-hour or medium defaults are applied.
- Topics do not create Calendar work until explicitly started. Start/Pause/Finish records actual learning time; revisions are earned through completed work.
- Exam dates and notification channels are unset; old settings and progress are not carried into this fresh dataset.

The coverage checklist mirrors the PDF architecture. It is not marked as independently
verified against the official UPSC syllabus. PDF factual summaries were not imported
as study notes or treated as verified knowledge. No subjects without a source PDF were
invented, so this is not a claim of complete UPSC syllabus coverage.

## Use The Dataset

The active tracker is already populated. Sign in and open **Subjects** or
**Strategy & Evidence**. You do not need to import the seed again.

To reset another installation, import [upsc_subjects_seed.json](upsc_subjects_seed.json)
through the application's Settings import control. Import replaces that installation's
data; export its current progress first.

## Rebuild From The PDFs

Install the PDF extraction dependency with the selected Python environment:

```powershell
python -m pip install -r requirements-seed.txt
python subject_seed.py
```

The default command regenerates only the reusable seed file. It refuses to overwrite
the active tracker path unless `--install` is supplied.

To back up and replace the active data, **stop all tracker servers first**, then run:

```powershell
python subject_seed.py --install
```

Installation archives the previous JSON under `%TEMP%/UPSC_TRACKER-backups`, uses an
atomic replacement for the active store, and verifies remote synchronization when
GitHub sync is configured. The original PDFs are not changed or deleted.

The extractor fails rather than silently importing an incomplete topic list when a
document's expected count changes. Run its tests with:

```powershell
python -m unittest test_subject_seed -v
```
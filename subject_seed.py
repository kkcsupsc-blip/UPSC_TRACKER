import argparse
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from preparation import DEFAULT_POLICY, validate_strategy


DOCUMENTS = (
    ("economy", "Economy", "ECONOMY/UPSC_Economy_Topic_Architecture_ENHANCED_V2.pdf", 37, "economy", "both", "#f2c94c"),
    ("environment", "Environment and Ecology", "ENVIRONMENT AND ECOLOGY/UPSC_Environment_Ecology_Topic_Architecture_ENHANCED.pdf", 21, "environment", "both", "#4ade80"),
    ("geography", "Geography", "GEOGRAPHY/UPSC_Geography_Topic_Architecture_ENHANCED.pdf", 35, "geography", "both", "#38bdf8"),
    ("modern-history", "Modern History", "MODERN_HISTORY/UPSC_Modern_History_Topic_Architecture_ENHANCED.pdf", 22, "history", "both", "#fb923c"),
    ("polity", "Polity and Governance", "POLITY/UPSC_Polity_Governance_Topic_Architecture_ENHANCED_v2.pdf", 57, "polity", "both", "#f472b6"),
    ("sociology-1", "Sociology Paper I", "SOCIOLOGY/PAPER 1/UPSC_Sociology_Paper1_Topic_Architecture.pdf", 18, "sociology1", "mains", "#2dd4bf"),
    ("sociology-2", "Sociology Paper II", "SOCIOLOGY/PAPER 2/UPSC_Sociology_Paper2_Topic_Architecture.pdf", 21, "sociology2", "mains", "#a3e635"),
)
HEADING = re.compile(r"^(\d{1,2}\.\d{1,2})\s+(.+)$")
LAYER = re.compile(r"^LAYER\s+(\d+)\s*[:\-]\s*(.+)$", re.IGNORECASE)
METADATA = re.compile(r"^(?:Pre[- ]requisites?|Inter[- ](?:dependencies|linkages)|Reading Protocol|Conceptual Weight|Exam Frequency|Prelims Importance|Mains Importance)\b", re.IGNORECASE)

RESOURCES = {
    "economy": [
        ("foundation", "NCERT Class 11 Indian Economic Development and Class 12 Introductory Macroeconomics", "Concept chapters corresponding to the numbered Economy topics", ""),
        ("spine", "Nitin Singhania - Indian Economy", "Topic-matched chapters; source PDF recommends 7th edition, 2026-27", ""),
        ("depth", "Economic Survey, Union Budget and RBI/NPCI releases", "Relevant chapter, table or official release for the current topic only", "Use for a current policy/data gap or a source-mapped PYQ error"),
    ],
    "environment": [
        ("foundation", "NCERT Class 12 Ecology unit", "Ecology and biodiversity foundations for the numbered topics", ""),
        ("spine", "Shankar IAS Environment OR PMF IAS Environment", "Choose one book only; read chapters mapped to the current topic", ""),
        ("depth", "MoEFCC, PIB, IUCN, UNFCCC and Ramsar official sources", "Dated legal/status/convention updates relevant to the current topic", "Verify a changing fact or repair a specific question gap"),
    ],
    "geography": [
        ("foundation", "NCERT Class 11 and 12 Geography - four books", "Physical and Indian Geography chapters mapped to the current topic", ""),
        ("spine", "G.C. Leong and an atlas", "Leong for climatology/landforms only; atlas for the current topic's locations", ""),
        ("depth", "Majid Husain - Geography of India", "Only relevant Indian resources, industry or economic-geography chapters", "Open only after PYQ analysis identifies a gap beyond NCERT"),
    ],
    "modern-history": [
        ("foundation", "NCERT Themes in Indian History Part III", "Analytical context for the numbered Modern History topics", ""),
        ("spine", "Spectrum - A Brief History of Modern India", "Topic-matched chapters, chronology and event matrices", ""),
        ("depth", "Bipan Chandra or Sekhar Bandyopadhyay", "One targeted analytical supplement for the current topic", "Repair an interpretation gap; reuse colonial-society reading for Sociology II"),
    ],
    "polity": [
        ("foundation", "NCERT Class 11 Indian Constitution at Work", "Constitutional reasoning for the corresponding topic", ""),
        ("spine", "M. Laxmikanth - Indian Polity", "Topic-matched chapters; source PDF recommends 8th edition", ""),
        ("depth", "Bare Constitution, PRS, D.D. Basu and landmark judgments", "Relevant provisions or one targeted legislative/doctrinal issue only", "Resolve a wording trap, current legal update or Mains reasoning gap"),
    ],
    "sociology-1": [
        ("foundation", "NCERT Sociology and IGNOU ESO", "Only concepts needing grounding before the numbered topic", ""),
        ("spine", "Nitin Sangwan - Essential Sociology", "Paper I chapters matched to the numbered source topics", ""),
        ("depth", "Ritzer, IGNOU MSO-001 or Haralambos", "Thinker depth or the specific institution/stratification section identified in the PDF", "Use where the source protocol or evaluated answer identifies insufficient depth"),
    ],
    "sociology-2": [
        ("foundation", "NCERT Class 12 Sociology", "Indian-society concepts relevant to the numbered topic", ""),
        ("spine", "Vikash Ranjan - Applied Sociology", "Paper II topic-matched chapters; Sangwan Vol 2 is a single-spine alternative", ""),
        ("depth", "Selected Indian sociologists and dated official survey data", "Only the authored study or data source relevant to the current topic", "Repair an argument/evidence gap; retain Paper I theory links and data dates"),
    ],
}


def clean_text(text):
    replacements = {"\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "}
    for original, replacement in replacements.items():
        text = text.replace(original, replacement)
    return re.sub(r"(?<=\d)-\s+(?=\d)", "-", " ".join(unicodedata.normalize("NFKC", text).split()))


def extract_topics(path):
    reader = PdfReader(path)
    topics = []
    layer_number, layer_name = None, None
    lines = []
    for page_number, page in enumerate(reader.pages, 1):
        for raw_line in (page.extract_text() or "").splitlines():
            line = clean_text(raw_line)
            if not line or re.fullmatch(r"Page \d+", line) or "Topic Architecture" in line:
                continue
            lines.append((page_number, line))
    for index, (page_number, line) in enumerate(lines):
        layer = LAYER.match(line)
        if layer:
            layer_number, layer_name = int(layer.group(1)), layer.group(2)
        heading = HEADING.match(line)
        if not heading:
            continue
        following = [entry[1] for entry in lines[index + 1:index + 5]]
        boundary = next((offset for offset, candidate in enumerate(following) if METADATA.match(candidate)), None)
        if boundary is None or not following[boundary].lower().startswith("pre"):
            continue
        name = " ".join([heading.group(2), *following[:boundary]])
        if not layer_number or int(heading.group(1).split(".")[0]) != layer_number:
            raise ValueError(f"Topic {heading.group(1)} has no matching layer on page {page_number}")
        topics.append({"code": heading.group(1), "name": name, "page": page_number,
                       "layerNumber": layer_number, "layerName": layer_name})
    codes = [topic["code"] for topic in topics]
    if len(codes) != len(set(codes)):
        raise ValueError(f"Duplicate topic headings in {path}")
    return topics


def extract_all(root):
    extracted = []
    for subject_id, name, filename, expected, profile, exam_type, color in DOCUMENTS:
        topics = extract_topics(Path(root) / filename)
        if len(topics) != expected:
            raise ValueError(f"{name}: expected {expected} main topics, extracted {len(topics)}")
        extracted.append({"id": subject_id, "name": name, "document": filename, "profile": profile,
                          "examType": exam_type, "color": color, "topics": topics})
    return extracted


def build_seed(root, defaults, extracted=None, created_at=None):
    root = Path(root)
    extracted = extracted if extracted is not None else extract_all(root)
    created_at = created_at or datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
    data = copy.deepcopy(defaults)
    data.update(subjects=[], completedRevisions={}, completedPractice={}, holidays=[],
                studyLogs=[], subjectCycles=[], assessmentAttempts=[], repairItems=[], activityHistory=[])
    data["cumulativeRevisions"] = {"sectionalBatches": [], "subjectRevisions": [], "pendingTopics": []}
    data["settings"]["preparation"] = dict(DEFAULT_POLICY)
    for document in extracted:
        subject = {
            "id": document["id"], "name": document["name"], "roi": "medium", "color": document["color"],
            "ntfyTopic": "", "defaultStages": None, "createdAt": created_at, "topics": [],
            "sourceDocument": document["document"],
            "notes": "Main numbered topics only, in source-document order. Initial hours and ROI are editable planning defaults, not PDF measurements.",
        }
        for item in document["topics"]:
            subject["topics"].append({
                "id": f"{document['id']}-{item['code'].replace('.', '-')}",
                "name": item["name"], "estimatedHours": 7.5, "roi": "medium", "examType": document["examType"],
                "status": "not-started", "startDate": None, "completionDate": None, "activeStages": None,
                "links": [], "relatedTopicIds": [], "prerequisiteIds": [], "createdAt": created_at,
                "notes": f"Topic {item['code']} | Layer {item['layerNumber']}: {item['layerName']} | PDF page {item['page']}",
                "source": {"document": document["document"], **item},
                "estimateSource": "initial-planning-default",
            })
        subject["strategy"] = validate_strategy({
            "profile": document["profile"], "stagePreset": "standard", "syllabusVerified": False,
            "resources": [{"tier": tier, "title": title, "scope": scope, "reason": reason}
                          for tier, title, scope, reason in RESOURCES[document["id"]]],
            "syllabus": [{"title": topic["name"], "topicIds": [topic["id"]]} for topic in subject["topics"]],
        }, subject)
        data["subjects"].append(subject)
    data["seedMetadata"] = {
        "topicLevelOnly": True, "subjectCount": len(extracted), "topicCount": sum(len(subject["topics"]) for subject in extracted),
        "createdAt": created_at, "estimatedHoursDefault": 7.5,
        "priorityBasis": "Neutral ROI preserves source-document topic order until priorities are calibrated",
        "syllabusBasis": "PDF topic architecture; not independently verified against the official syllabus",
        "documents": [{"path": subject["document"], "topicCount": len(subject["topics"]),
                       "sha256": hashlib.sha256((root / subject["document"]).read_bytes()).hexdigest()}
                      for subject in extracted],
    }
    validate_seed(data)
    return data


def validate_seed(data):
    if len(data["subjects"]) != len(DOCUMENTS):
        raise ValueError("The seed must contain all seven subject documents")
    ids = set()
    for subject, specification in zip(data["subjects"], DOCUMENTS):
        if subject["id"] != specification[0] or len(subject["topics"]) != specification[3]:
            raise ValueError(f"Topic count or subject order mismatch: {specification[1]}")
        validate_strategy(subject["strategy"], subject)
        for topic in subject["topics"]:
            if topic["id"] in ids or topic["status"] != "not-started":
                raise ValueError("Seed topic IDs must be unique and all topics unstarted")
            if topic["examType"] != specification[5] or not re.fullmatch(r"\d+\.\d+", topic["source"]["code"]):
                raise ValueError("Seed must use main topic headings and the correct exam type")
            if any(topic.get(key) for key in ("startDate", "completionDate", "links", "relatedTopicIds", "prerequisiteIds")):
                raise ValueError("Seed topics must not inherit old progress or links")
            ids.add(topic["id"])
    for key in ("completedRevisions", "completedPractice", "studyLogs", "subjectCycles", "assessmentAttempts", "repairItems", "activityHistory"):
        if data.get(key):
            raise ValueError(f"Old progress must not remain in {key}")
    return data


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as output:
            temporary_path = output.name
            json.dump(data, output, indent=2, ensure_ascii=True, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def main():
    parser = argparse.ArgumentParser(description="Build a fresh tracker from main numbered PDF topics only")
    parser.add_argument("--output", default="data/upsc_subjects_seed.json")
    parser.add_argument("--install", action="store_true", help="Back up and replace the active tracker data; stop tracker servers first")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent
    extracted = extract_all(root)
    import app
    data = build_seed(root, app.default_data(), extracted=extracted)
    output = Path(arguments.output)
    output = output if output.is_absolute() else root / output
    if output.resolve() == Path(app.DATA_FILE).resolve() and not arguments.install:
        parser.error("Replacing active tracker data requires --install")
    if arguments.install and Path(app.DATA_FILE).exists():
        backup_dir = Path(tempfile.gettempdir()) / "UPSC_TRACKER-backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = backup_dir / f"tracker_data-before-subject-reset-{stamp}.json"
        shutil.copy2(app.DATA_FILE, backup)
        print(f"Previous data backup: {backup}")
    write_json(output, data)
    if arguments.install:
        app.save_data(data)
        app._wait_for_pending_push()
        if app.GITHUB_TOKEN and app.GITHUB_REPO:
            remote, _ = app._gh_fetch_data()
            if remote != data:
                raise RuntimeError("Local reset is installed, but GitHub sync could not be verified. Do not restart with remote restore enabled until synchronized.")
        print("Fresh subject seed installed as the active tracker data.")
    for subject in data["subjects"]:
        print(f"{subject['name']}: {len(subject['topics'])} main topics")
    print(f"Total: {data['seedMetadata']['topicCount']} main topics. Reusable JSON: {output}")


if __name__ == "__main__":
    main()
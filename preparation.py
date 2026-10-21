import math
from datetime import date, timedelta
from uuid import uuid4

from flask import Blueprint, jsonify, request


PROFILES = {
    "general": {"name": "General GS", "outputs": ["Concept recall", "Question application"]},
    "economy": {"name": "Economy", "outputs": ["Mechanism explanation", "Policy application"]},
    "polity": {"name": "Polity and Governance", "outputs": ["Rules and exceptions", "Institutional comparison"]},
    "environment": {"name": "Environment and Ecology", "outputs": ["Ecological mechanism", "Dated factual verification"]},
    "geography": {"name": "Geography", "outputs": ["Blank-map recall", "Annotated diagram"]},
    "history": {"name": "Modern History", "outputs": ["Chronology recall", "Cause and consequence"]},
    "sociology1": {"name": "Sociology Paper I", "outputs": ["Thinker comparison", "Evaluated theoretical argument"]},
    "sociology2": {"name": "Sociology Paper II", "outputs": ["Indian study application", "Paper I linkage"]},
    "csat": {"name": "CSAT", "outputs": ["Timed problem solving", "Comprehension accuracy"]},
    "essay": {"name": "Essay", "outputs": ["Coherent outline", "Evaluated timed essay"]},
    "ethics": {"name": "Ethics", "outputs": ["Concept application", "Case-study judgement"]},
}

DEFAULT_POLICY = {
    "mcqAccuracy": 70, "recallAccuracy": 70, "writingPercent": 50,
    "minMcqQuestions": 20, "minRecallItems": 5, "delayedRecallDays": 7,
    "freshDays": 21,
}
ERROR_TYPES = ("concept", "fact", "application", "elimination", "time", "structure", "evidence", "map", "chronology")


def number(value, label, minimum=0, maximum=100000, integer=False):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number") from None
    if not math.isfinite(result) or not minimum <= result <= maximum or (integer and not result.is_integer()):
        raise ValueError(f"{label} is outside the allowed range")
    return int(result) if integer else result


def validate_attempt(body, subject, today):
    if not isinstance(body, dict) or body.get("kind") not in ("mcq", "writing", "recall", "skill"):
        raise ValueError("Choose an assessment type")
    topic_id = body.get("topicId") or None
    if topic_id and topic_id not in {topic["id"] for topic in subject["topics"]}:
        raise ValueError("Choose a topic from this subject")
    try:
        attempted = date.fromisoformat(body.get("date", today))
    except (TypeError, ValueError):
        raise ValueError("Choose a valid assessment date") from None
    if attempted > date.fromisoformat(today):
        raise ValueError("Assessment dates cannot be in the future")
    attempt = {
        "id": uuid4().hex, "subjectId": subject["id"], "topicId": topic_id,
        "date": attempted.isoformat(), "kind": body["kind"],
        "minutes": number(body.get("minutes", 0), "Minutes", maximum=1440),
        "notes": str(body.get("notes", ""))[:2000],
        "setType": body.get("setType", "diagnostic"),
        "skill": str(body.get("skill", ""))[:200],
    }
    if attempt["setType"] not in ("diagnostic", "unseen", "mixed", "repeated"):
        raise ValueError("Choose a valid question-set type")
    errors = body.get("errors", [])
    if not isinstance(errors, list) or any(error not in ERROR_TYPES for error in errors):
        raise ValueError("Choose valid error categories")
    attempt["errors"] = list(dict.fromkeys(errors))
    if attempt["kind"] == "writing":
        attempt["maxMarks"] = number(body.get("maxMarks", 10), "Maximum marks", minimum=0.1)
        score = body.get("score")
        attempt["score"] = None if score in (None, "") else number(score, "Awarded marks", maximum=attempt["maxMarks"])
        attempt["reviewer"] = body.get("reviewer", "unreviewed")
        if attempt["reviewer"] not in ("unreviewed", "self", "external"):
            raise ValueError("Choose an evaluation source")
        if attempt["reviewer"] == "unreviewed":
            attempt["score"] = None
        elif attempt["score"] is None:
            raise ValueError("An evaluated answer needs awarded marks")
    else:
        for field in ("correct", "wrong", "unattempted"):
            attempt[field] = number(body.get(field, 0), field.title(), integer=True)
        total = attempt["correct"] + attempt["wrong"] + attempt["unattempted"]
        if total == 0:
            raise ValueError("Record at least one question or recall item")
        if attempt["kind"] == "skill" and not attempt["skill"]:
            raise ValueError("Name the subject skill being checked")
        attempt["marksPerQuestion"] = number(body.get("marksPerQuestion", 2), "Marks per question", minimum=0.01, maximum=100)
        attempt["penaltyFraction"] = number(body.get("penaltyFraction", 1 / 3), "Wrong-answer penalty", maximum=1)
        attempt["total"] = total
        answered = attempt["correct"] + attempt["wrong"]
        attempt["accuracy"] = round(100 * attempt["correct"] / answered, 1) if answered else 0
        attempt["retrievalPercent"] = round(100 * attempt["correct"] / total, 1)
        attempt["netMarks"] = round(attempt["marksPerQuestion"] * (
            attempt["correct"] - attempt["wrong"] * attempt["penaltyFraction"]), 2) if attempt["kind"] == "mcq" else None
    return attempt


def evidence_summary(data, topic, today):
    policy = {**DEFAULT_POLICY, **data.get("settings", {}).get("preparation", {})}
    attempts = [entry for entry in data.get("assessmentAttempts", [])
                if entry.get("topicId") == topic["id"] and not entry.get("voided")]
    dimensions = {}
    for kind in ("mcq", "writing", "recall", "skill"):
        records = sorted((entry for entry in attempts if entry["kind"] == kind), key=lambda entry: entry["date"])
        latest = records[-1] if records else None
        status = "not-assessed"
        if latest:
            status = "needs-practice"
            if kind == "writing":
                if latest.get("reviewer") == "self":
                    status = "self-assessed"
                elif latest.get("reviewer") != "external" or latest.get("score") is None:
                    status = "not-assessed"
                elif latest["minutes"] > 0 and latest["score"] / latest["maxMarks"] * 100 >= policy["writingPercent"]:
                    status = "on-target"
            elif kind == "mcq":
                if latest["setType"] not in ("unseen", "mixed"):
                    status = "diagnostic-only"
                elif latest["correct"] + latest["wrong"] < policy["minMcqQuestions"]:
                    status = "small-sample"
                elif latest["accuracy"] >= policy["mcqAccuracy"] and latest["minutes"] > 0:
                    status = "on-target"
            elif kind == "recall":
                completion = topic.get("completionDate")
                delayed = completion and (date.fromisoformat(latest["date"]) - date.fromisoformat(completion)).days >= policy["delayedRecallDays"]
                if not delayed:
                    status = "early-recall"
                elif latest["total"] < policy["minRecallItems"]:
                    status = "small-sample"
                elif latest["retrievalPercent"] >= policy["recallAccuracy"]:
                    status = "on-target"
            else:
                status = "recorded"
            age = (date.fromisoformat(today) - date.fromisoformat(latest["date"])).days
            if status == "on-target" and age > policy["freshDays"]:
                status = "stale"
        dimensions[kind] = {"status": status, "latest": latest, "attempts": len(records)}
    repairs = [entry for entry in data.get("repairItems", [])
               if entry.get("topicId") == topic["id"] and entry.get("status") == "open"]
    return {"dimensions": dimensions, "openRepairs": len(repairs), "attempts": len(attempts)}


def strategy_stages(subject, topic, fallback):
    preset = topic.get("studyScope", subject.get("strategy", {}).get("stagePreset", "standard"))
    if preset != "compact":
        return fallback
    selected = {"R1", "PYQ", "ERA", "R3", "R30", "MCQ", "MCQA", "MAINS"}
    return [stage for stage in fallback if stage in selected]


def subject_coverage(subject):
    topics = {topic["id"]: topic for topic in subject["topics"]}
    items = subject.get("strategy", {}).get("syllabus", [])
    covered = sum(bool(item.get("topicIds")) and all(
        topics.get(topic_id, {}).get("status") in ("completed", "pipeline-complete")
        for topic_id in item["topicIds"]
    ) for item in items)
    return {"total": len(items), "covered": covered,
            "verified": subject.get("strategy", {}).get("syllabusVerified", False)}


def validate_strategy(body, subject):
    profile = body.get("profile", "general")
    if profile not in PROFILES:
        raise ValueError("Choose a valid subject profile")
    preset = body.get("stagePreset", "standard")
    if preset not in ("standard", "compact"):
        raise ValueError("Choose standard or compact activities")
    resources = body.get("resources", [])
    syllabus = body.get("syllabus", [])
    if not isinstance(resources, list) or len(resources) > 20:
        raise ValueError("Use at most 20 bounded resources")
    if not isinstance(syllabus, list) or len(syllabus) > 200:
        raise ValueError("Use at most 200 syllabus entries")
    clean_resources = []
    for resource in resources:
        if not isinstance(resource, dict) or resource.get("tier") not in ("foundation", "spine", "depth"):
            raise ValueError("Each resource needs a valid reading tier")
        title = str(resource.get("title", "")).strip()[:200]
        scope = str(resource.get("scope", "")).strip()[:600]
        reason = str(resource.get("reason", "")).strip()[:600]
        if not title or not scope:
            raise ValueError("Each resource needs a title and bounded chapters or scope")
        if resource["tier"] == "depth" and not reason:
            raise ValueError("Depth reading needs an identified gap or question")
        clean_resources.append({"title": title, "scope": scope, "tier": resource["tier"], "reason": reason})
    topic_ids = {topic["id"] for topic in subject["topics"]}
    clean_syllabus = []
    for item in syllabus:
        if not isinstance(item, dict) or not str(item.get("title", "")).strip():
            raise ValueError("Each syllabus entry needs a title")
        linked = item.get("topicIds", [])
        if not isinstance(linked, list) or any(topic_id not in topic_ids for topic_id in linked):
            raise ValueError("Syllabus entries must link to topics in this subject")
        clean_syllabus.append({"title": str(item["title"]).strip()[:500], "topicIds": list(dict.fromkeys(linked))})
    return {"profile": profile, "stagePreset": preset, "resources": clean_resources,
            "syllabus": clean_syllabus, "syllabusVerified": body.get("syllabusVerified") is True}


def validate_prerequisites(data, topic_id, prerequisites):
    topics = {topic["id"]: topic for subject in data["subjects"] for topic in subject["topics"]}
    if not isinstance(prerequisites, list) or any(
        not isinstance(entry, str) or entry not in topics or entry == topic_id for entry in prerequisites
    ):
        raise ValueError("Prerequisites must be other existing topics")
    graph = {key: topic.get("prerequisiteIds", []) for key, topic in topics.items()}
    graph[topic_id] = prerequisites
    visited, pending = set(), set()

    def visit(key):
        if key in pending:
            raise ValueError("Prerequisites cannot contain a cycle")
        if key in visited:
            return
        pending.add(key)
        for dependency in graph.get(key, []):
            visit(dependency)
        pending.remove(key)
        visited.add(key)

    for key in graph:
        visit(key)
    return list(dict.fromkeys(prerequisites))


def create_preparation_blueprint(load_data, save_data, today, reconcile):
    blueprint = Blueprint("preparation", __name__)

    @blueprint.route("/api/preparation", methods=["GET"])
    def overview():
        data = load_data()
        return jsonify({"profiles": PROFILES, "policy": {**DEFAULT_POLICY, **data.get("settings", {}).get("preparation", {})},
                        "errorTypes": ERROR_TYPES, "repairs": data.get("repairItems", []), "subjects": [
            {"id": subject["id"], "name": subject["name"], "strategy": subject.get("strategy", {}),
             "coverage": subject_coverage(subject), "topics": [
                 {**topic, "evidence": evidence_summary(data, topic, today())} for topic in subject["topics"]
             ], "attempts": [entry for entry in data.get("assessmentAttempts", [])
                              if entry["subjectId"] == subject["id"] and not entry.get("voided")]}
            for subject in data["subjects"]
        ]})

    @blueprint.route("/api/preparation/policy", methods=["PUT"])
    def save_policy():
        data = load_data()
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Expected training targets"}), 400
        try:
            policy = {key: number(body.get(key, default), key, minimum=1,
                                  maximum=100 if key.endswith(("Accuracy", "Percent")) else 365,
                                  integer=True) for key, default in DEFAULT_POLICY.items()}
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        data.setdefault("settings", {})["preparation"] = policy
        save_data(data)
        return jsonify({"ok": True})

    @blueprint.route("/api/subjects/<subject_id>/attempts", methods=["POST"])
    def add_attempt(subject_id):
        data = load_data()
        subject = next((subject for subject in data["subjects"] if subject["id"] == subject_id), None)
        if not subject:
            return jsonify({"error": "Subject not found"}), 404
        try:
            attempt = validate_attempt(request.get_json(silent=True), subject, today())
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        data.setdefault("assessmentAttempts", []).append(attempt)
        for category in attempt["errors"]:
            data.setdefault("repairItems", []).append({
                "id": uuid4().hex, "subjectId": subject_id, "topicId": attempt["topicId"],
                "attemptId": attempt["id"], "category": category, "status": "open",
                "dueDate": (date.fromisoformat(today()) + timedelta(days=2)).isoformat(),
            })
        save_data(data)
        return jsonify(attempt), 201

    @blueprint.route("/api/preparation/attempts/<attempt_id>", methods=["DELETE"])
    def void_attempt(attempt_id):
        data = load_data()
        attempt = next((entry for entry in data.get("assessmentAttempts", []) if entry["id"] == attempt_id), None)
        if not attempt:
            return jsonify({"error": "Assessment not found"}), 404
        attempt["voided"] = True
        for repair in data.get("repairItems", []):
            if repair["attemptId"] == attempt_id and repair["status"] == "open":
                repair["status"] = "cancelled"
        save_data(data)
        return jsonify({"ok": True})

    @blueprint.route("/api/preparation/repairs/<repair_id>", methods=["PUT"])
    def resolve_repair(repair_id):
        data = load_data()
        repair = next((entry for entry in data.get("repairItems", []) if entry["id"] == repair_id), None)
        if not repair:
            return jsonify({"error": "Repair task not found"}), 404
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not str(body.get("resolution", "")).strip():
            return jsonify({"error": "Record the correction and retest outcome"}), 400
        repair.update(status="resolved", resolution=str(body["resolution"]).strip()[:2000], resolvedDate=today())
        save_data(data)
        return jsonify({"ok": True})

    @blueprint.route("/api/subjects/<subject_id>/strategy", methods=["PUT"])
    def save_strategy(subject_id):
        data = load_data()
        subject = next((subject for subject in data["subjects"] if subject["id"] == subject_id), None)
        if not subject:
            return jsonify({"error": "Subject not found"}), 404
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Expected a strategy object"}), 400
        try:
            strategy = validate_strategy(body, subject)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        subject["strategy"] = strategy
        for topic in subject["topics"]:
            reconcile(data, topic)
        save_data(data)
        return jsonify({"ok": True, "coverage": subject_coverage(subject)})

    @blueprint.route("/api/subjects/<subject_id>/topics/<topic_id>/strategy", methods=["PUT"])
    def save_topic_strategy(subject_id, topic_id):
        data = load_data()
        subject = next((subject for subject in data["subjects"] if subject["id"] == subject_id), None)
        topic = next((topic for topic in subject["topics"] if topic["id"] == topic_id), None) if subject else None
        if not topic:
            return jsonify({"error": "Topic not found"}), 404
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or body.get("studyScope") not in ("inherit", "standard", "compact"):
            return jsonify({"error": "Choose a valid activity scope"}), 400
        try:
            prerequisites = validate_prerequisites(data, topic_id, body.get("prerequisiteIds", []))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        if body["studyScope"] == "inherit":
            topic.pop("studyScope", None)
        else:
            topic["studyScope"] = body["studyScope"]
        topic["prerequisiteIds"] = prerequisites
        reconcile(data, topic)
        save_data(data)
        return jsonify({"ok": True})

    return blueprint
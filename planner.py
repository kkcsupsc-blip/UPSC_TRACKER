import copy
from datetime import date, datetime, timedelta, timezone
import math


STREAMS = ("gs", "optional")
POOLS = ("gs", "optional", "recall", "practice", "currentAffairs")
DEFAULT_PLANNER = {
    "mode": "two-stream",
    "attemptYear": 2028,
    "phase": "auto",
    "prelimsFocusDays": 112,
    "recallGuardDays": 7,
    "weekendConsolidation": True,
    "gsSubjectOrder": [],
    "optionalSubjectOrder": [],
    "allocations": {
        "integrated": {"gs": 40, "optional": 26.67, "recall": 15.56, "practice": 11.11, "currentAffairs": 6.66},
        "prelims": {"gs": 35, "optional": 5, "recall": 25, "practice": 30, "currentAffairs": 5},
        "mains": {"gs": 10, "optional": 10, "recall": 20, "practice": 55, "currentAffairs": 5},
    },
}


def subject_stream(subject):
    explicit = subject.get("studyStream")
    if explicit in STREAMS:
        return explicit
    profile = subject.get("strategy", {}).get("profile", "")
    name = subject.get("name", "").lower()
    return "optional" if profile in ("sociology1", "sociology2") or "sociology" in name or "optional" in name else "gs"


def planner_settings(settings):
    result = copy.deepcopy(DEFAULT_PLANNER)
    supplied = settings.get("planner", {})
    if not isinstance(supplied, dict):
        return result
    for key in result:
        if key != "allocations" and key in supplied:
            result[key] = supplied[key]
    allocations = supplied.get("allocations", {})
    if isinstance(allocations, dict):
        for phase, values in allocations.items():
            if phase in result["allocations"] and isinstance(values, dict):
                result["allocations"][phase].update({key: value for key, value in values.items() if key in POOLS})
    return result


def validate_planner(body, subjects):
    if not isinstance(body, dict):
        raise ValueError("Expected planner settings")
    allocations = body.get("allocations", {})
    if not isinstance(allocations, dict) or any(
        phase not in DEFAULT_PLANNER["allocations"] or not isinstance(values, dict) or set(values) - set(POOLS)
        for phase, values in allocations.items()
    ):
        raise ValueError("Choose valid phase allocation fields")
    result = planner_settings({"planner": body})
    result["mode"] = "two-stream"
    if result["phase"] not in ("auto", "integrated", "prelims", "mains"):
        raise ValueError("Choose a valid preparation phase")
    for key, minimum, maximum in (("attemptYear", 2026, 2100), ("prelimsFocusDays", 14, 365), ("recallGuardDays", 0, 90)):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"Invalid {key}")
    result["weekendConsolidation"] = result["weekendConsolidation"] is True
    for phase, values in result["allocations"].items():
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               or not 0 <= value <= 100 for value in values.values()) or abs(sum(values.values()) - 100) > 0.01:
            raise ValueError(f"{phase} allocations must total 100 percent")
        if values["gs"] <= 0 or values["optional"] <= 0:
            raise ValueError("Both learning streams need a positive allocation")
    for stream, key in (("gs", "gsSubjectOrder"), ("optional", "optionalSubjectOrder")):
        allowed = {subject["id"] for subject in subjects if subject_stream(subject) == stream}
        order = result[key]
        if not isinstance(order, list) or any(not isinstance(value, str) or value not in allowed for value in order) or len(order) != len(set(order)):
            raise ValueError(f"Invalid {stream} subject order")
    return result


def preparation_phase(day, settings, config):
    if config["phase"] != "auto":
        return config["phase"]
    exams = settings.get("examDates", {})
    prelims, mains = exams.get("prelims"), exams.get("mains")
    if prelims and day > prelims and (not mains or day <= mains):
        return "mains"
    if prelims and 0 <= (date.fromisoformat(prelims) - date.fromisoformat(day)).days <= config["prelimsFocusDays"]:
        return "prelims"
    return "integrated"


def daily_quotas(budget, weights, fixed_hours=0, actual_by_pool=None):
    quotas = {pool: max(0, budget) * weights[pool] / 100 for pool in POOLS}
    fixed_remaining = min(max(0, fixed_hours), max(0, budget))
    for pool in ("recall", "practice", "gs", "optional", "currentAffairs"):
        consumed = min(quotas[pool], fixed_remaining)
        quotas[pool] -= consumed
        fixed_remaining -= consumed
    for pool, spent in (actual_by_pool or {}).items():
        if pool not in quotas:
            continue
        remaining = max(0, spent)
        for candidate in (pool, *[entry for entry in POOLS if entry != pool]):
            consumed = min(quotas[candidate], remaining)
            quotas[candidate] -= consumed
            remaining -= consumed
    return quotas


def learning_split(available, needs, weights):
    active = [stream for stream in STREAMS if needs.get(stream, 0) > 0.0001]
    result = {stream: 0.0 for stream in STREAMS}
    remaining = max(0, available)
    while active and remaining > 0.0001:
        total_weight = sum(weights[stream] for stream in active)
        assigned = 0
        for stream in active:
            share = remaining * (weights[stream] / total_weight if total_weight else 1 / len(active))
            hours = min(share, needs[stream] - result[stream])
            result[stream] += hours
            assigned += hours
        remaining -= assigned
        active = [stream for stream in active if needs[stream] - result[stream] > 0.0001]
    return result


STAGES = ("R1", "PYQ", "ERA", "R3", "MN", "MCQ", "MCQA", "R7", "MVA", "MAINS", "R30")
RECALL = {"R1", "R3", "R7", "R30"}
LABELS = {
    "R1": "1st Revision (Recall)", "PYQ": "PYQ Practice", "ERA": "Error Analysis",
    "R3": "2nd Revision (Active Recall)", "MN": "Micro Note Making",
    "MCQ": "MCQ Practice", "MCQA": "MCQ Analysis", "R7": "Weekend Consolidation",
    "MVA": "Mains Value Addition", "MAINS": "Mains Answer Writing", "R30": "Final Revision",
}
EPSILON = 0.0000001


def _hours(value):
    try:
        number = float(value)
        return max(0.0, number) if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def log_stage(log):
    stage = log.get("stage") or log.get("revType") or log.get("type")
    stage = stage.upper() if isinstance(stage, str) else None
    return stage if stage in STAGES else "learning"


def _date(value):
    try:
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone(timedelta(hours=5, minutes=30)))
            return parsed.date().isoformat()
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            seconds = value / 1000 if value > 100000000000 else value
            return datetime.fromtimestamp(seconds, timezone(timedelta(hours=5, minutes=30))).date().isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return None


def _add(day, offset):
    return (date.fromisoformat(day) + timedelta(days=offset)).isoformat()


def _subject_order(subject, config):
    stream = subject_stream(subject)
    explicit = config["gsSubjectOrder" if stream == "gs" else "optionalSubjectOrder"]
    if subject["id"] in explicit:
        return (0, explicit.index(subject["id"]), "", "")
    profiles = ("economy", "environment", "geography", "history", "polity", "sociology1", "sociology2")
    profile = subject.get("strategy", {}).get("profile", "")
    if profile not in profiles:
        name = subject.get("name", "").lower()
        profile = next((key for key in profiles[:5] if key in name), "")
        if stream == "optional":
            profile = "sociology2" if any(token in name for token in (" ii", " 2", "paper-2")) else "sociology1"
    return (1, profiles.index(profile) if profile in profiles else len(profiles),
            subject.get("name", "").lower(), subject["id"])


def _fixed_activities(data):
    events = {}
    settings = data.get("settings", {})
    batch_hours = _hours(settings.get("activityHours", {}).get("sectionalBatch", 12)) / 2
    for batch in data.get("cumulativeRevisions", {}).get("sectionalBatches", []):
        for session in batch.get("sessions", []):
            first = _date(session.get("scheduledDate"))
            if session.get("completed") or not first:
                continue
            for day in (first, _add(first, 1)):
                events.setdefault(day, []).append({
                    "category": "cumulative_sectional", "batchId": batch.get("id"),
                    "round": session.get("round"), "topicCount": len(batch.get("topicIds", [])),
                    "hours": batch_hours, "done": False, "label": "Sectional retrieval",
                    "subjectName": batch.get("subjectName", "Sectional retrieval"),
                })
    for cycle in data.get("subjectCycles", []):
        first, last = _date(cycle.get("startDate")), _date(cycle.get("endDate"))
        if cycle.get("completed") or not first or not last:
            continue
        for offset in range(min(3650, max(0, (date.fromisoformat(last) - date.fromisoformat(first)).days + 1))):
            events.setdefault(_add(first, offset), []).append({
                "category": "subject_cycle", "cycleId": cycle.get("id"),
                "subjectId": cycle.get("subjectId"), "subjectName": cycle.get("subjectName", "Subject"),
                "cycle": cycle.get("cycle"), "label": cycle.get("label", "Subject retrieval"),
                "hours": _hours(cycle.get("hoursPerDay")), "done": False,
            })
    return events


def empty_day(data, day, config=None):
    config = config or planner_settings(data.get("settings", {}))
    settings = data.get("settings", {})
    weekend = date.fromisoformat(day).weekday() >= 5 or day in data.get("holidays", [])
    budget = _hours(settings.get("weekendHours", 12) if weekend else settings.get("weekdayHours", 6))
    return {
        "date": day, "isWeekend": weekend, "budget": budget, "totalHours": 0.0,
        "totalDemand": 0.0, "remaining": budget, "overloaded": False, "overloadHours": 0.0,
        "spilloverHours": 0.0, "spilloverItems": [], "activities": [], "revisionHours": 0.0,
        "learningHours": 0.0, "cumulativeHours": 0.0, "utilization": 0,
        "schedulingErrors": [], "phase": preparation_phase(day, settings, config),
        "streams": {stream: {"topicId": None, "topicName": None, "subjectId": None,
                             "subjectName": None, "hours": 0.0, "remaining": 0.0,
                             "isSuggested": False} for stream in STREAMS},
    }


def _finish_day(load):
    activities = load["activities"]
    load["totalHours"] = round(sum(item["hours"] for item in activities if not item.get("displayOnly")), 6)
    load["totalDemand"] = round(load["totalHours"] + load["spilloverHours"], 6)
    load["remaining"] = round(max(0, load["budget"] - load["totalHours"]), 6)
    load["overloadHours"] = round(max(0, load["totalDemand"] - load["budget"]), 6)
    load["overloaded"] = load["overloadHours"] > EPSILON
    load["actualHours"] = round(sum(item["hours"] for item in activities if item.get("isActual") and not item.get("displayOnly")), 6)
    load["estimatedSpentHours"] = round(sum(item["hours"] for item in activities if item.get("isEstimatedActual")), 6)
    load["plannedHours"] = round(max(0, load["totalHours"] - load["actualHours"] - load["estimatedSpentHours"]), 6)
    load["utilization"] = round(min(100, load["totalHours"] / load["budget"] * 100)) if load["budget"] else 0
    for field, categories in (("learningHours", {"learning"}), ("revisionHours", {"revision"}),
                              ("cumulativeHours", {"cumulative_sectional", "subject_cycle"})):
        load[field] = round(sum(item["hours"] for item in activities
                                if item["category"] in categories and not item.get("displayOnly")), 6)
    for stream, lane in load["streams"].items():
        entries = [item for item in activities if item["category"] == "learning" and item["stream"] == stream]
        if entries:
            last = entries[-1]
            lane.update({key: last[key] for key in ("topicId", "topicName", "subjectId", "subjectName", "remaining", "isSuggested")})
            lane["hours"] = round(sum(item["hours"] for item in entries), 6)
    return load


def build_plan(data, today, stage_hours_callback, topic_stages_callback, confidence_callback=None):
    """Build a pure, finite plan shared by daily views and forecasts.

    Callbacks accept (data, topic), (data, topic_id), and optionally
    (data, topic_id, previous_recall_stage), respectively. Stage hours are a map.
    Learning logs have no stage; partial stage logs use stage/type/revType.
    """
    settings = data.get("settings", {})
    config = planner_settings(settings)
    intervals = {"r1": 1, "r3": 5, "r7": 14, "r30": 35, **settings.get("intervals", {})}
    completed = data.get("completedRevisions", {})
    nodes, by_id, errors, warnings = [], {}, [], []
    logs = {}
    for log in data.get("studyLogs", []):
        day = _date(log.get("date"))
        if day and day <= today:
            logs.setdefault((log.get("topicId"), log_stage(log)), []).append((day, _hours(log.get("hours"))))
    for subject in sorted(data.get("subjects", []), key=lambda item: _subject_order(item, config)):
        for topic in subject.get("topics", []):
            topic_id = topic["id"]
            learned = topic.get("status") in ("completed", "pipeline-complete")
            learning_logs = logs.get((topic_id, "learning"), [])
            logged = sum(hours for _, hours in learning_logs)
            remaining = 0 if learned else max(0, _hours(topic.get("estimatedHours", 7.5)) - logged)
            requested = list(dict.fromkeys(topic_stages_callback(data, topic_id)))
            active = [stage for stage in STAGES if stage in requested] + [stage for stage in requested if stage not in STAGES]
            durations = stage_hours_callback(data, topic)
            node = {
                "topic": topic, "subject": subject, "stream": subject_stream(subject),
                "remaining": remaining, "initialRemaining": remaining, "learned": learned,
                "learningDate": _date(topic.get("completionDate")) if learned else None,
                "startDate": topic.get("startDate") if topic.get("status") != "not-started" else None,
                "stages": {}, "order": len(nodes),
            }
            for stage in active:
                key = f"{topic_id}_{stage}"
                record = completed.get(key)
                done = key in completed
                actual_date = _date(record.get("completedAt") if isinstance(record, dict) else record) if done else None
                partial = logs.get((topic_id, stage), [])
                progress = topic.get("stageProgress", {}).get(stage, 0)
                if isinstance(progress, dict):
                    progress = progress.get("hours", progress.get("completedHours", 0))
                spent = max(_hours(progress), sum(hours for _, hours in partial))
                stored = topic.get("revisionSchedule", {}).get(stage.lower())
                if isinstance(stored, dict):
                    stored = stored.get("originalDate") or stored.get("dueDate") or stored.get("date")
                node["stages"][stage] = {
                    "date": actual_date, "type": stage, "label": LABELS.get(stage, stage),
                    "sessions": [], "remaining": 0 if done else max(0, _hours(durations.get(stage, 1)) - spent),
                    "done": done, "originalDate": _date(stored), "dueDate": None,
                    "isProjected": not learned, "canMark": learned, "hours": _hours(durations.get(stage, 1)),
                    "remainingHours": 0 if done else max(0, _hours(durations.get(stage, 1)) - spent),
                }
            nodes.append(node)
            by_id[topic_id] = node
    for stream in STREAMS:
        active = [node for node in nodes if node["stream"] == stream and node["topic"].get("status") == "learning"]
        if len(active) > 1:
            warnings.append({"stream": stream, "topicIds": [node["topic"]["id"] for node in active],
                             "warning": "Multiple active topics in one stream; advancing one at a time without resetting progress"})
    fixed = _fixed_activities(data)
    latest_fixed = max([today, *[day for day in fixed if day >= today]])
    days = {}
    lanes = {stream: None for stream in STREAMS}
    paused_streams = {}
    weekly_hours = _hours(settings.get("weekdayHours", 6)) * 5 + _hours(settings.get("weekendHours", 12)) * 2

    def prerequisites_ready(node, day):
        return all(dependency in by_id and by_id[dependency]["learningDate"]
                   and by_id[dependency]["learningDate"] <= day
                   for dependency in node["topic"].get("prerequisiteIds", []))

    def learner(stream, day):
        current = lanes[stream]
        if current and not current["learningDate"]:
            return current
        candidates = [node for node in nodes if node["stream"] == stream and not node["learningDate"]
                      and not node["learned"] and (not node["startDate"] or node["startDate"] <= day)
                      and (stream not in paused_streams or node["startDate"] or node["topic"].get("status") == "learning")
                      and prerequisites_ready(node, day)]
        return min(candidates, key=lambda node: (node["topic"].get("status") != "learning",
                                                 node["startDate"] or today, node["order"]), default=None)

    def earliest(node, stage):
        anchor = node["learningDate"]
        if not anchor:
            return None
        selected = node["stages"]
        dependencies = {
            "R1": (), "PYQ": ("R1",), "ERA": ("PYQ", "R1"),
            "R3": ("R1",), "MN": ("R3", "ERA", "PYQ", "R1"),
            "MCQ": ("MN", "R3", "R1"), "MCQA": ("MCQ",),
            "R7": ("MCQA", "MCQ", "MN", "R3", "R1"),
            "MVA": ("ERA", "PYQ", "R1"), "MAINS": ("MVA", "ERA", "PYQ", "R1"),
            "R30": ("R7", "R3", "R1"),
        }.get(stage, ())
        if stage in ("ERA", "MCQ", "R7", "MVA", "MAINS", "R30"):
            dependencies = (next((entry for entry in dependencies if entry in selected), ""),)
        dates = []
        for dependency in dependencies:
            if dependency not in selected:
                continue
            value = selected[dependency]["date"]
            if not value:
                return None
            dates.append(value)
        previous = {"R3": "R1", "R7": "R3", "R30": "R7"}.get(stage)
        multiplier = _hours(confidence_callback(data, node["topic"]["id"], previous)) if confidence_callback and previous else 1
        offset = max(0, round(_hours(intervals.get(stage.lower(), 0)) * multiplier)) if stage in RECALL else 0
        gap = {"R3": 1, "MN": 1, "MCQ": 1, "R7": 5, "MVA": 1, "MAINS": 1, "R30": 7}.get(stage, 0)
        candidate = max([_add(anchor, offset), *[_add(value, gap) for value in dates]])
        if stage == "R7" and config["weekendConsolidation"]:
            while date.fromisoformat(candidate).weekday() < 5:
                candidate = _add(candidate, 1)
        return candidate

    def activity(node, hours, category, **extra):
        topic, subject = node["topic"], node["subject"]
        return {"category": category, "topicId": topic["id"], "topicName": topic["name"],
                "subjectId": subject["id"], "subjectName": subject["name"],
                "subjectColor": subject.get("color", ""), "stream": node["stream"],
                "hours": round(hours, 6), "done": False, **extra}

    def learning_session(node, day, hours, load, actual=False):
        if not actual:
            node["remaining"] = max(0, node["remaining"] - hours)
            lanes[node["stream"]] = node
            if not node["startDate"]:
                node["startDate"] = day
            if node["remaining"] <= EPSILON:
                node["learningDate"] = day
        load["activities"].append(activity(
            node, hours, "learning", remaining=round(node["remaining"], 6),
            isSuggested=node["topic"].get("status") != "learning" and not node["learned"],
            isActual=actual, isProjected=not actual,
        ))

    def place_stages(day, load, quotas, borrow=False):
        def ready(pool, stream):
            candidates = []
            for node in nodes:
                if node["stream"] != stream:
                    continue
                for stage, step in node["stages"].items():
                    if step["done"] or step["date"] or ("recall" if stage in RECALL else "practice") != pool:
                        continue
                    due = earliest(node, stage)
                    if not due:
                        continue
                    step["dueDate"] = due
                    step["originalDate"] = step["originalDate"] or due
                    if due > day or (stage == "R7" and config["weekendConsolidation"]
                                     and date.fromisoformat(day).weekday() < 5):
                        continue
                    candidates.append((step["originalDate"], due, node["order"], STAGES.index(stage), node, stage, step))
            return sorted(candidates, key=lambda candidate: candidate[:4])

        for pool in ("recall", "practice"):
            sources = [pool] + ([stream for stream in STREAMS if learner(stream, day) is None] if borrow else [])
            needs = {stream: sum(candidate[-1]["remaining"] for candidate in ready(pool, stream)) for stream in STREAMS}
            shares = learning_split(sum(quotas[source] for source in sources), needs, config["allocations"][load["phase"]])
            for stream in STREAMS:
                allowance = shares[stream]
                while True:
                    candidates = ready(pool, stream)
                    if not candidates:
                        break
                    _, _, _, _, node, stage, step = candidates[0]
                    if step["remaining"] <= EPSILON:
                        step["date"] = day
                        continue
                    spend = min(step["remaining"], allowance)
                    if spend <= EPSILON:
                        break
                    outstanding = spend
                    for source in sources:
                        amount = min(outstanding, quotas[source])
                        quotas[source] -= amount
                        outstanding -= amount
                    allowance -= spend
                    step["remaining"] = max(0, step["remaining"] - spend)
                    step["sessions"].append({"date": day, "hours": round(spend, 6)})
                    load["activities"].append(activity(
                        node, spend, "revision", revType=stage, type=stage,
                        label=step["label"] if node["learned"] and day <= today else f"Estimated {step['label']}",
                        isProjected=not node["learned"] or day > today, canMark=node["learned"],
                        originalDate=step["originalDate"], overdue=node["learned"] and step["originalDate"] < today,
                        stageRemaining=round(step["remaining"], 6),
                    ))
                    if step["remaining"] <= EPSILON:
                        step["date"] = day

    for offset in range(3650):
        day = _add(today, offset)
        load = empty_day(data, day, config)
        paused_streams = {}
        guard = config.get("recallGuardDays", 7)
        if guard:
            for node in nodes:
                for stage, step in node["stages"].items():
                    if stage not in RECALL or step["done"] or step["date"]:
                        continue
                    due = earliest(node, stage)
                    if due:
                        delay = (date.fromisoformat(day) - date.fromisoformat(due)).days
                        if delay > guard:
                            paused_streams[node["stream"]] = max(paused_streams.get(node["stream"], 0), delay)
        load["backlogGuard"] = dict(paused_streams)
        fixed_today = fixed.get(day, [])
        actual_by_pool = {}
        for node in nodes:
            for log_day, hours in logs.get((node["topic"]["id"], "learning"), []):
                if log_day == day:
                    learning_session(node, day, hours, load, actual=True)
                    actual_by_pool[node["stream"]] = actual_by_pool.get(node["stream"], 0) + hours
            for stage, step in node["stages"].items():
                for log_day, hours in logs.get((node["topic"]["id"], stage), []):
                    if log_day == day:
                        pool = "recall" if stage in RECALL else "practice"
                        actual_by_pool[pool] = actual_by_pool.get(pool, 0) + hours
                        load["activities"].append(activity(node, hours, "revision", revType=stage,
                                                           type=stage, label=step["label"], isActual=True,
                                                           isProjected=False, canMark=node["learned"]))
                if step["done"] and step["date"] == day:
                    stage_logs = logs.get((node["topic"]["id"], stage), [])
                    estimated_spent = 0 if day != today or any(log_day == day for log_day, _ in stage_logs) else max(
                        0, step["hours"] - sum(hours for log_day, hours in stage_logs if log_day < day))
                    if estimated_spent > EPSILON:
                        pool = "recall" if stage in RECALL else "practice"
                        actual_by_pool[pool] = actual_by_pool.get(pool, 0) + estimated_spent
                    load["activities"].append(activity(
                        node, estimated_spent, "revision", revType=stage, type=stage,
                        label=step["label"] + (" (estimated time used)" if estimated_spent else ""),
                        done=True, displayOnly=estimated_spent <= EPSILON, isActual=False,
                        isEstimatedActual=estimated_spent > EPSILON, isProjected=False, canMark=node["learned"],
                    ))
        actual_hours = sum(actual_by_pool.values())
        available_fixed = max(0, load["budget"] - actual_hours)
        for entry in fixed_today:
            hours = min(entry["hours"], available_fixed)
            available_fixed -= hours
            load["activities"].append({**entry, "hours": round(hours, 6)})
            excess = entry["hours"] - hours
            if excess > EPSILON:
                load["spilloverHours"] += excess
                load["spilloverItems"].append({**entry, "hours": excess})
                errors.append({"date": day, "error": "Fixed reservations exceed daily budget capacity"})
        fixed_hours = sum(item["hours"] for item in load["activities"] if item["category"] in ("subject_cycle", "cumulative_sectional"))
        quotas = daily_quotas(load["budget"], config["allocations"][load["phase"]], fixed_hours, actual_by_pool)
        place_stages(day, load, quotas)
        for stream in STREAMS:
            while True:
                node = learner(stream, day)
                if node is None:
                    break
                if node["remaining"] <= EPSILON:
                    node["learningDate"] = day
                    node["startDate"] = node["startDate"] or day
                    continue
                spend = min(node["remaining"], quotas[stream])
                if spend <= EPSILON:
                    break
                quotas[stream] -= spend
                learning_session(node, day, spend, load)
        for stream in STREAMS:
            other = "optional" if stream == "gs" else "gs"
            while other not in paused_streams and learner(other, day) is None and quotas[other] > EPSILON:
                node = learner(stream, day)
                if node is None:
                    break
                spend = min(node["remaining"], quotas[other])
                quotas[other] -= spend
                learning_session(node, day, spend, load)
        place_stages(day, load, quotas, borrow=True)
        unfinished = any(not node["learningDate"] or any(not step["date"] for step in node["stages"].values()) for node in nodes)
        if unfinished or any(not item.get("displayOnly") for item in load["activities"]):
            for pool, label in (("recall", "Retrieval practice"), ("practice", "Practice and answer writing"),
                                ("currentAffairs", "Current affairs")):
                if quotas[pool] > EPSILON:
                    load["activities"].append({"category": "reserve", "pool": pool, "subjectName": label,
                                               "label": label, "hours": round(quotas[pool], 6), "done": False})
            for stream in paused_streams:
                if quotas[stream] > EPSILON:
                    load["activities"].append({"category": "reserve", "pool": "recall", "stream": stream,
                                               "subjectName": "Recall backlog recovery", "label": "Recall backlog recovery",
                                               "hours": round(quotas[stream], 6), "done": False})
        days[day] = _finish_day(load)
        if (not unfinished and day >= latest_fixed) or weekly_hours == 0:
            break

    estimates, schedules = {}, {}
    for node in nodes:
        topic, subject = node["topic"], node["subject"]
        schedule = node["stages"]
        for stage, step in schedule.items():
            if not step["originalDate"]:
                step["originalDate"] = earliest(node, stage)
            step.pop("remaining")
        def finish(selected):
            dates = [node["learningDate"], *[step["date"] for stage, step in schedule.items() if stage in selected]]
            return max(dates) if dates and all(dates) else None
        mastery = finish(schedule)
        error = None
        if not mastery:
            error = ("No study hours configured; set weekday or weekend hours above zero" if weekly_hours == 0 else
                     "Unscheduled work: missing dates, impossible dependencies or task pools, or exceeds the 3650-day planning horizon")
            errors.append({"topicId": topic["id"], "error": error})
        estimates[topic["id"]] = {
            "topicName": topic["name"], "subjectId": subject["id"], "subjectName": subject["name"],
            "subjectColor": subject.get("color", ""), "roi": topic.get("roi", "medium"),
            "startDate": node["startDate"], "completionDate": node["learningDate"], "masteryDate": mastery,
            "revisionSchedule": {stage.lower(): step["date"] for stage, step in schedule.items()},
            "doneRevisions": sum(step["done"] for step in schedule.values()), "status": topic.get("status", "not-started"),
            "isEstimate": not node["learned"], "queuePosition": node["order"] + 1, "schedulingError": error,
            "stream": node["stream"],
            "prelimsFinishDate": finish(set(schedule) - {"MVA", "MAINS"})
            if node["stream"] == "gs" and topic.get("examType", "both") != "mains" else None,
            "mainsFinishDate": finish(schedule) if topic.get("examType", "both") != "prelims" else None,
        }
        schedules[topic["id"]] = {stage.lower(): step for stage, step in schedule.items()}
    def complete_date(values):
        return max(values) if values and all(values) else None
    streams = {}
    for stream in STREAMS:
        members = [node for node in nodes if node["stream"] == stream]
        streams[stream] = {
            "coverageDate": complete_date([node["learningDate"] for node in members]),
            "pipelineDate": complete_date([estimates[node["topic"]["id"]]["masteryDate"] for node in members]),
            "totalTopics": len(members), "learningHours": round(sum(node["initialRemaining"] for node in members), 6),
        }
    milestones = {"optional": {key: streams["optional"][key] for key in ("coverageDate", "pipelineDate")}}
    for exam in ("prelims", "mains"):
        exam_date = _date(settings.get("examDates", {}).get(exam))
        deadline = _add(exam_date, -int(_hours(settings.get("examBufferDays", 0)))) if exam_date else None
        members = [node for node in nodes if (exam == "mains" and node["topic"].get("examType", "both") != "prelims")
                   or (exam == "prelims" and node["stream"] == "gs" and node["topic"].get("examType", "both") != "mains")]
        late, unknown, dates = [], [], []
        for node in members:
            topic, subject = node["topic"], node["subject"]
            finish_date = estimates[topic["id"]][f"{exam}FinishDate"]
            dates.append(finish_date)
            entry = {"topicId": topic["id"], "topicName": topic["name"], "subjectName": subject["name"]}
            if not finish_date:
                unknown.append(entry)
            elif deadline and finish_date > deadline:
                late.append(entry)
        milestones[exam] = {"finishDate": complete_date(dates), "deadline": deadline,
                            "lateTopics": late, "unscheduledTopics": unknown}
    planned = {"learning": 0.0, "revision": 0.0, "cumulative": 0.0, "reserve": 0.0, "total": 0.0}
    for load in days.values():
        load["schedulingErrors"] = errors
        for item in load["activities"]:
            if item.get("isActual") or item.get("isEstimatedActual"):
                continue
            category = "cumulative" if item["category"] in ("subject_cycle", "cumulative_sectional") else item["category"]
            planned[category] += item["hours"]
            planned["total"] += item["hours"]
    summary = {
        "totalTopics": len(nodes), "inPipeline": sum(not node["learned"] for node in nodes),
        "notStarted": sum(node["topic"].get("status") == "not-started" for node in nodes),
        "learning": sum(node["topic"].get("status") == "learning" for node in nodes),
        "overallFinishDate": complete_date([entry["masteryDate"] for entry in estimates.values()]),
        "parallelSlots": 2, "simulationDays": len(days), "weeklyStudyHours": weekly_hours,
        "remainingLearningHours": round(sum(node["initialRemaining"] for node in nodes), 6),
        "remainingFollowUpHours": round(sum(step["remainingHours"] for node in nodes
                           for step in node["stages"].values() if not step["done"]), 6),
        "scheduledTopics": sum(bool(entry["masteryDate"]) for entry in estimates.values()),
        "unscheduledTopics": sum(not entry["masteryDate"] for entry in estimates.values()),
        "schedulingErrors": errors, "warnings": warnings, "streams": streams, "milestones": milestones,
        "plannerConfig": config, "attemptYear": config["attemptYear"],
        "phase": preparation_phase(today, settings, config),
        "plannedHours": {key: round(value, 6) for key, value in planned.items()},
        "totalPlannedHours": round(planned["total"], 6),
        "provisionalTopics": sum(not node["learned"] and node["topic"].get("estimateSource") not in ("user-estimate", "actual-logged") for node in nodes),
        "provisionalCount": sum(not node["learned"] and node["topic"].get("estimateSource") not in ("user-estimate", "actual-logged") for node in nodes),
        "backlogGuardDays": config.get("recallGuardDays", 7),
        "guardedLearningDays": {stream: sum(stream in load.get("backlogGuard", {}) for load in days.values()) for stream in STREAMS},
        "recallPressure": {stream: {
            "maxDelayDays": max([0, *[(date.fromisoformat(step["sessions"][0]["date"]) - date.fromisoformat(step["originalDate"])).days
                                     for node in nodes if node["stream"] == stream
                                     for stage, step in node["stages"].items()
                                     if stage in RECALL and step["sessions"] and step["originalDate"]]]),
        } for stream in STREAMS},
    }
    return {"estimates": estimates, "summary": summary, "schedules": schedules, "days": days}


def plan_day(plan, data, day):
    """Read a planned day, or display immutable actuals outside the forecast."""
    if day in plan["days"]:
        return copy.deepcopy(plan["days"][day])
    else:
        load = empty_day(data, day, plan["summary"]["plannerConfig"])
        load["schedulingErrors"] = copy.deepcopy(plan["summary"]["schedulingErrors"])
        topics = {topic["id"]: (topic, subject) for subject in data.get("subjects", []) for topic in subject.get("topics", [])}
        for log in data.get("studyLogs", []):
            topic_id = log.get("topicId")
            if _date(log.get("date")) != day or topic_id not in topics:
                continue
            topic, subject = topics[topic_id]
            stage = log_stage(log)
            revision = stage != "learning"
            remaining = max(0, _hours(topic.get("estimatedHours", 7.5)) - sum(
                _hours(entry.get("hours")) for entry in data.get("studyLogs", [])
                if entry.get("topicId") == topic_id and (_date(entry.get("date")) or "9999") <= day
                and log_stage(entry) == "learning"))
            load["activities"].append({
                "category": "revision" if revision else "learning", "topicId": topic_id,
                "topicName": topic["name"], "subjectId": subject["id"], "subjectName": subject["name"],
                "subjectColor": subject.get("color", ""), "stream": subject_stream(subject),
                "hours": _hours(log.get("hours")), "isActual": True, "isProjected": False,
                "isSuggested": False, "remaining": remaining, "done": False,
                **({"revType": stage, "type": stage, "label": LABELS[stage],
                    "canMark": bool(topic.get("completionDate"))} if revision else {}),
            })
    for subject in data.get("subjects", []):
        for topic in subject.get("topics", []):
            for step in plan["schedules"].get(topic["id"], {}).values():
                if step["done"] and step["date"] == day:
                    load["activities"].append({
                        "category": "revision", "topicId": topic["id"], "topicName": topic["name"],
                        "subjectId": subject["id"], "subjectName": subject["name"],
                        "subjectColor": subject.get("color", ""), "stream": subject_stream(subject),
                        "revType": step["type"], "type": step["type"], "label": step["label"],
                        "hours": 0.0, "done": True, "displayOnly": True, "isProjected": False,
                        "canMark": step["canMark"],
                    })
    return _finish_day(load)
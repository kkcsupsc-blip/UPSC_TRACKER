import copy

from flask import Blueprint, jsonify, request

from planner import _subject_order, planner_settings, preparation_phase, subject_stream, validate_planner


def create_planner_blueprint(load_data, save_data, today):
    blueprint = Blueprint("study_planner", __name__)

    @blueprint.route("/api/planner", methods=["GET"])
    def get_planner():
        data = load_data()
        settings = data["settings"]
        config = planner_settings(settings)
        subjects = sorted(data["subjects"], key=lambda subject: (subject_stream(subject), _subject_order(subject, config)))
        return jsonify({
            "config": config,
            "subjects": [{"id": subject["id"], "name": subject["name"], "stream": subject_stream(subject),
                          "learningTopics": sum(topic["status"] == "learning" for topic in subject["topics"])}
                         for subject in subjects],
            "phase": preparation_phase(today(), settings, config),
            "weeklyStudyHours": 5 * settings.get("weekdayHours", 6) + 2 * settings.get("weekendHours", 12),
        })

    @blueprint.route("/api/planner", methods=["PUT"])
    def save_planner():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("config"), dict):
            return jsonify({"error": "Expected planner configuration"}), 400
        data = load_data()
        updated = copy.deepcopy(data)
        subjects = {subject["id"]: subject for subject in updated["subjects"]}
        streams = body.get("subjectStreams", {})
        if not isinstance(streams, dict) or any(subject_id not in subjects or stream not in ("gs", "optional")
                                                for subject_id, stream in streams.items()):
            return jsonify({"error": "Invalid subject stream assignment"}), 400
        original_counts = {stream: sum(topic["status"] == "learning" for subject in data["subjects"]
                                       if subject_stream(subject) == stream for topic in subject["topics"])
                           for stream in ("gs", "optional")}
        for subject_id, stream in streams.items():
            subjects[subject_id]["studyStream"] = stream
        for stream in ("gs", "optional"):
            count = sum(topic["status"] == "learning" for subject in updated["subjects"]
                        if subject_stream(subject) == stream for topic in subject["topics"])
            if count > max(1, original_counts[stream]):
                return jsonify({"error": f"This assignment creates multiple active {stream.upper()} learners; complete learning first"}), 409
        try:
            config = validate_planner(body["config"], updated["subjects"])
        except (TypeError, ValueError, AttributeError) as error:
            return jsonify({"error": str(error)}), 400
        updated["settings"]["planner"] = config
        save_data(updated)
        return jsonify({"ok": True, "config": config})

    return blueprint
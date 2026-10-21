import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from flask import Flask, request

from test_preparation import isolated_backend


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.backend = isolated_backend()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Path(self.directory.name) / "tracker_data.json"
        self.backend.update(
            DATA_DIR=self.directory.name, DATA_FILE=str(self.store),
            GITHUB_TOKEN="", GITHUB_REPO="", _first_load=False,
            _data_lock=threading.RLock(),
            _push_lock=threading.Lock(), _queued_push=None, _pending_push=None,
        )
        self.push = Mock()
        self.queue_push = self.backend["_gh_push_async"]
        self.backend["_gh_push_async"] = self.push
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_replace_failure_preserves_store_and_cleans_temporary_file(self):
        original = b'{"subjects": [], "version": 3}'
        self.store.write_bytes(original)
        with patch("os.replace", side_effect=OSError("replace failed")) as replace:
            with self.assertRaisesRegex(OSError, "replace failed"):
                self.backend["save_data"]({"subjects": [], "version": 4})
        self.assertEqual(Path(replace.call_args.args[0]).parent, self.store.parent)
        self.assertEqual(self.store.read_bytes(), original)
        self.assertEqual(list(self.store.parent.iterdir()), [self.store])
        self.push.assert_not_called()

    def test_serialization_failure_preserves_store(self):
        self.store.write_text('{"version": 3}', encoding="utf-8")
        with self.assertRaises(TypeError):
            self.backend["save_data"]({"invalid": object()})
        self.assertEqual(json.loads(self.store.read_text(encoding="utf-8")), {"version": 3})
        self.assertEqual(list(self.store.parent.iterdir()), [self.store])
        self.push.assert_not_called()

    def test_flush_failure_preserves_store(self):
        self.store.write_bytes(b'{"version": 3}')
        with patch("os.fsync", side_effect=OSError("flush failed")):
            with self.assertRaisesRegex(OSError, "flush failed"):
                self.backend["save_data"]({"version": 4})
        self.assertEqual(self.store.read_bytes(), b'{"version": 3}')
        self.assertEqual(list(self.store.parent.iterdir()), [self.store])
        self.push.assert_not_called()

    def test_successful_save_replaces_json_then_queues_sync(self):
        data = {"subjects": [], "version": 3}
        self.backend["save_data"](data)
        self.assertEqual(json.loads(self.store.read_text(encoding="utf-8")), data)
        self.assertEqual(list(self.store.parent.iterdir()), [self.store])
        self.push.assert_called_once_with(data)

    def test_malformed_store_raises_without_resetting_data(self):
        for original in (b'{"subjects": [', b'\xff', b'[]', b'null', b'{"settings": null}'):
            with self.subTest(original=original):
                self.store.write_bytes(original)
                with self.assertRaises(RuntimeError):
                    self.backend["load_data"]()
                self.assertEqual(self.store.read_bytes(), original)
        self.push.assert_not_called()

    def test_unreadable_store_raises_instead_of_returning_defaults(self):
        self.store.write_text('{}', encoding="utf-8")
        with patch("builtins.open", side_effect=PermissionError("read denied")):
            with self.assertRaises(RuntimeError) as failure:
                self.backend["load_data"]()
        self.assertIsInstance(failure.exception.__cause__, PermissionError)
        self.assertEqual(self.store.read_bytes(), b'{}')
        self.push.assert_not_called()

    def test_missing_store_initializes_defaults(self):
        data = self.backend["load_data"]()
        self.assertEqual(data, self.backend["default_data"]())
        self.assertEqual(json.loads(self.store.read_text(encoding="utf-8")), data)
        self.push.assert_called_once()

    def test_first_load_retains_corruption_even_with_github_enabled(self):
        self.backend.update(GITHUB_TOKEN="test-only", GITHUB_REPO="test/repo", _first_load=True)
        self.backend["_gh_fetch_data"] = Mock()
        self.store.write_bytes(b'{"subjects": [')
        with self.assertRaises(RuntimeError):
            self.backend["load_data"]()
        self.assertEqual(self.store.read_bytes(), b'{"subjects": [')
        self.backend["_gh_fetch_data"].assert_not_called()
        self.push.assert_not_called()

    def test_failed_integrity_check_does_not_persist_partial_migration(self):
        data = self.backend["default_data"]()
        data["subjects"] = [{"topics": [{"id": "missing-status"}]}]
        data["cumulativeRevisions"]["subjectRevisions"] = [{"id": "legacy"}]
        original = json.dumps(data).encode("utf-8")
        self.store.write_bytes(original)
        with self.assertRaises(RuntimeError):
            self.backend["load_data"]()
        self.assertEqual(self.store.read_bytes(), original)
        self.push.assert_not_called()

    def test_first_load_restores_github_atomically_once(self):
        self.backend.update(GITHUB_TOKEN="test-only", GITHUB_REPO="test/repo", _first_load=True)
        self.store.write_text(json.dumps(self.backend["default_data"]()), encoding="utf-8")
        remote = self.backend["default_data"]()
        remote["subjects"] = [{"id": "remote", "topics": []}]
        self.backend["_gh_fetch_data"] = Mock(return_value=(remote, "test-sha"))
        with patch("os.replace", wraps=self.backend["os"].replace) as replace:
            restored = self.backend["load_data"]()
        self.assertEqual(restored["subjects"][0]["id"], "remote")
        self.assertEqual(json.loads(self.store.read_text(encoding="utf-8")), restored)
        replace.assert_called_once()
        self.assertEqual(Path(replace.call_args.args[0]).parent, self.store.parent)
        self.assertEqual(self.backend["load_data"](), restored)
        self.backend["_gh_fetch_data"].assert_called_once()
        self.push.assert_not_called()

    def test_invalid_github_snapshot_leaves_local_store_unchanged(self):
        self.backend.update(GITHUB_TOKEN="test-only", GITHUB_REPO="test/repo", _first_load=True)
        original = json.dumps(self.backend["default_data"]()).encode("utf-8")
        self.store.write_bytes(original)
        self.backend["_gh_fetch_data"] = Mock(return_value=({"subjects": [None]}, "test-sha"))
        with self.assertRaises(RuntimeError):
            self.backend["load_data"]()
        self.assertEqual(self.store.read_bytes(), original)
        self.push.assert_not_called()

    def test_github_unavailable_falls_back_to_local_store(self):
        self.backend.update(GITHUB_TOKEN="test-only", GITHUB_REPO="test/repo", _first_load=True)
        data = self.backend["default_data"]()
        self.store.write_text(json.dumps(data), encoding="utf-8")
        self.backend["_gh_fetch_data"] = Mock(return_value=(None, None))
        self.assertEqual(self.backend["load_data"](), data)
        self.push.assert_not_called()

    def test_save_before_first_load_cannot_restore_stale_remote_data(self):
        self.backend.update(GITHUB_TOKEN="test-only", GITHUB_REPO="test/repo", _first_load=True)
        remote = self.backend["default_data"]()
        remote["subjects"] = [{"id": "stale", "topics": []}]
        self.backend["_gh_fetch_data"] = Mock(return_value=(remote, "test-sha"))
        latest = self.backend["default_data"]()
        latest["subjects"] = [{"id": "latest", "topics": []}]
        self.backend["save_data"](latest)
        self.assertEqual(self.backend["load_data"]()["subjects"][0]["id"], "latest")
        self.backend["_gh_fetch_data"].assert_not_called()

    def test_legacy_revision_history_is_preserved_without_rewriting(self):
        data = self.backend["default_data"]()
        data["cumulativeRevisions"]["subjectRevisions"] = [{"id": "legacy"}]
        self.store.write_text(json.dumps(data), encoding="utf-8")
        loaded = self.backend["load_data"]()
        self.assertEqual(loaded["cumulativeRevisions"]["subjectRevisions"], [{"id": "legacy"}])
        self.assertEqual(json.loads(self.store.read_text(encoding="utf-8")), loaded)
        self.push.assert_not_called()

    def request_app(self, before_lock=None, authenticate=False):
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="test-only")
        if authenticate:
            app.before_request(self.backend["require_login"])
            app.add_url_rule("/login", endpoint="login_page", view_func=lambda: "login")
        if before_lock:
            app.before_request(before_lock)
        app.before_request(self.backend["_lock_data_request"])
        app.teardown_request(self.backend["_unlock_data_request"])
        return app

    def test_real_subject_endpoint_preserves_auth_and_persists(self):
        app = self.request_app(authenticate=True)
        app.add_url_rule("/api/subjects", view_func=self.backend["api_add_subject"], methods=["POST"])
        with app.test_client() as client:
            denied = client.post("/api/subjects", json={"name": "Not authenticated"})
            self.assertEqual(denied.status_code, 302)
            self.assertFalse(self.store.exists())
            with client.session_transaction() as session:
                session["logged_in"] = True
            response = client.post("/api/subjects", json={"name": "Economy"})
        self.assertGreaterEqual(response.status_code, 200)
        self.assertLess(response.status_code, 300)
        self.assertEqual(self.backend["load_data"]()["subjects"][0]["name"], "Economy")

    def test_concurrent_mutations_keep_both_updates(self):
        self.assert_serialized_mutations("POST")

    def test_read_repairs_cannot_overwrite_in_flight_mutations(self):
        self.assert_serialized_mutations("GET")

    def assert_serialized_mutations(self, second_method):
        self.backend["save_data"]({"subjects": [], "counter": 0})
        first_loaded = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        second_loaded = threading.Event()
        responses = []

        def mark_request_started():
            if request.path.endswith("/second"):
                second_started.set()

        app = self.request_app(before_lock=mark_request_started)

        def mutate(label):
            data = self.backend["load_data"]()
            if label == "first":
                first_loaded.set()
                self.assertTrue(release_first.wait(3))
            else:
                second_loaded.set()
            data["counter"] += 1
            self.backend["save_data"](data)
            return "ok"

        app.add_url_rule("/api/mutate/<label>", view_func=mutate, methods=["POST", "GET"])

        def send(label):
            with app.test_client() as client:
                method = "POST" if label == "first" else second_method
                responses.append(client.open(f"/api/mutate/{label}", method=method).status_code)

        first = threading.Thread(target=send, args=("first",))
        second = threading.Thread(target=send, args=("second",))
        first.start()
        try:
            self.assertTrue(first_loaded.wait(3))
            second.start()
            self.assertTrue(second_started.wait(3))
            self.assertFalse(second_loaded.wait(0.1))
        finally:
            release_first.set()
            first.join(3)
            if second.ident is not None:
                second.join(3)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(responses, [200, 200])
        self.assertEqual(self.backend["load_data"]()["counter"], 2)

    def test_teardown_releases_lock_after_error_and_repeated_teardown(self):
        app = self.request_app()

        def fail():
            raise ValueError("route failed")

        app.add_url_rule("/api/fail", view_func=fail, methods=["POST"])
        with app.test_client() as client:
            with self.assertRaisesRegex(ValueError, "route failed"):
                client.post("/api/fail")
        acquired = []

        def check_lock():
            locked = self.backend["_data_lock"].acquire(timeout=1)
            acquired.append(locked)
            if locked:
                self.backend["_data_lock"].release()

        checker = threading.Thread(target=check_lock)
        checker.start()
        checker.join(2)
        self.assertEqual(acquired, [True])

    def test_github_worker_serializes_coalesces_and_copies_snapshots(self):
        self.backend.update(GITHUB_TOKEN="test-only", GITHUB_REPO="test/repo")
        first_started = threading.Event()
        release_first = threading.Event()
        observed = []

        def push(snapshot):
            observed.append(snapshot)
            if snapshot["version"] == 1:
                first_started.set()
                if not release_first.wait(3):
                    raise AssertionError("First push was not released")

        self.backend["_gh_push_data"] = Mock(side_effect=push)
        self.queue_push({"version": 1})
        try:
            self.assertTrue(first_started.wait(3))
            worker = self.backend["_pending_push"]
            self.queue_push({"version": 2})
            latest = {"version": 3, "subjects": [{"topics": []}]}
            self.queue_push(latest)
            latest["subjects"][0]["topics"].append("not in snapshot")
            self.assertIs(self.backend["_pending_push"], worker)
            self.assertEqual(len(observed), 1)
        finally:
            release_first.set()
            self.backend["_wait_for_pending_push"]()
        self.assertEqual(observed, [
            {"version": 1}, {"version": 3, "subjects": [{"topics": []}]},
        ])
        self.assertIsNone(self.backend["_pending_push"])
        self.assertIsNone(self.backend["_queued_push"])
        self.queue_push({"version": 4})
        self.backend["_wait_for_pending_push"]()
        self.assertEqual(observed[-1], {"version": 4})

    def test_github_worker_continues_to_latest_after_push_error(self):
        self.backend.update(GITHUB_TOKEN="test-only", GITHUB_REPO="test/repo")
        first_started = threading.Event()
        release_first = threading.Event()

        def push(snapshot):
            if snapshot["version"] == 1:
                first_started.set()
                if not release_first.wait(3):
                    raise AssertionError("First push was not released")
                raise OSError("mock network failure")

        self.backend["_gh_push_data"] = Mock(side_effect=push)
        self.queue_push({"version": 1})
        try:
            self.assertTrue(first_started.wait(3))
            self.queue_push({"version": 2})
        finally:
            release_first.set()
            self.backend["_wait_for_pending_push"]()
        self.assertEqual(
            self.backend["_gh_push_data"].call_args_list,
            [unittest.mock.call({"version": 1}), unittest.mock.call({"version": 2})],
        )
        self.assertIsNone(self.backend["_pending_push"])

    def test_disabled_github_sync_starts_no_thread(self):
        with patch("threading.Thread") as worker:
            self.queue_push({"version": 1})
        worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
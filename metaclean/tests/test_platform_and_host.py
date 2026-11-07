import os
import sys
import tempfile
import unittest
from unittest import mock
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app as metaclean


class PlatformAndHostTests(unittest.TestCase):
    def setUp(self):
        self.client = metaclean.app.test_client()
        self.previous_host = dict(metaclean.HOSTING)

    def tearDown(self):
        with metaclean.HOSTING_LOCK:
            metaclean.HOSTING.update(self.previous_host)

    def test_dashboard_is_local_only_even_when_hosting_is_enabled(self):
        with metaclean.HOSTING_LOCK:
            metaclean.HOSTING.update(enabled=True, token="test-secret")
        response = self.client.get(
            "/",
            base_url="http://192.168.1.20:5000",
            environ_overrides={"REMOTE_ADDR": "192.168.1.30"},
        )
        self.assertEqual(response.status_code, 403)

    def test_private_lan_portal_requires_valid_share_token(self):
        with metaclean.HOSTING_LOCK:
            metaclean.HOSTING.update(enabled=True, token="test-secret")
        denied = self.client.get(
            "/remote?access=wrong",
            base_url="http://192.168.1.20:5000",
            environ_overrides={"REMOTE_ADDR": "192.168.1.30"},
        )
        self.assertEqual(denied.status_code, 403)
        allowed = self.client.get(
            "/remote?access=test-secret",
            base_url="http://192.168.1.20:5000",
            environ_overrides={"REMOTE_ADDR": "192.168.1.30"},
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertIn(b"Clean files using this host", allowed.data)

    def test_public_client_cannot_use_host_portal(self):
        with metaclean.HOSTING_LOCK:
            metaclean.HOSTING.update(enabled=True, token="test-secret")
        response = self.client.get(
            "/remote?access=test-secret",
            base_url="http://192.168.1.20:5000",
            environ_overrides={"REMOTE_ADDR": "8.8.8.8"},
        )
        self.assertEqual(response.status_code, 403)

    def test_server_listener_is_available_on_all_network_interfaces(self):
        self.assertEqual(metaclean.BIND_HOST, "0.0.0.0")

    def test_host_status_builds_share_link_for_detected_lan_ip(self):
        with metaclean.HOSTING_LOCK:
            metaclean.HOSTING.update(enabled=True, token="lan-secret")
        with mock.patch.object(metaclean, "lan_ipv4_addresses", return_value=["192.168.1.44"]):
            status = metaclean.host_status()
        self.assertEqual(
            status["urls"],
            ["http://192.168.1.44:5000/remote?access=lan-secret"],
        )

    def test_termux_host_toggle_requests_and_releases_android_wake_lock(self):
        previous = metaclean.IS_TERMUX
        try:
            metaclean.IS_TERMUX = True
            with mock.patch.object(
                metaclean, "set_termux_wake_lock",
                side_effect=[
                    {"ok": True, "message": "Android wake lock active."},
                    {"ok": True, "message": "Android wake lock released."},
                ],
            ) as wake_lock:
                headers = {"X-MC-Token": metaclean.TOKEN}
                started = self.client.post(
                    "/api/host", json={"enabled": True}, headers=headers
                )
                self.assertEqual(started.status_code, 200)
                self.assertTrue(started.get_json()["host"]["enabled"])
                self.assertTrue(started.get_json()["host"]["wake_lock"]["ok"])

                stopped = self.client.post(
                    "/api/host", json={"enabled": False}, headers=headers
                )
                self.assertEqual(stopped.status_code, 200)
                self.assertFalse(stopped.get_json()["host"]["enabled"])
                self.assertEqual(wake_lock.call_args_list, [mock.call(True), mock.call(False)])
        finally:
            metaclean.IS_TERMUX = previous

    def test_termux_disables_mat2_and_uses_native_fallback_plan(self):
        old_termux = metaclean.IS_TERMUX
        old_cache = dict(metaclean._TOOLS)
        try:
            metaclean.IS_TERMUX = True
            data = metaclean.tools(force=True)
            self.assertFalse(data["mat2"]["available"])
            self.assertIn("disabled on Termux", data["mat2"]["error"])
            fake = {
                "exiftool": {"available": True},
                "mat2": {"available": False},
                "ffmpeg": {"available": True},
                "qpdf": {"available": True},
            }
            self.assertEqual(metaclean.plan_for("image", ".jpg", "auto", fake), ["exiftool"])
            self.assertEqual(metaclean.plan_for("video", ".mp4", "auto", fake), ["ffmpeg", "exiftool"])
        finally:
            metaclean.IS_TERMUX = old_termux
            metaclean._TOOLS.clear()
            metaclean._TOOLS.update(old_cache)

    def test_delete_original_runs_only_after_cleaner_success(self):
        with tempfile.TemporaryDirectory() as folder:
            original = os.path.join(folder, "photo.jpg")
            output = os.path.join(folder, "photo.cleaned.jpg")
            with open(original, "wb") as handle:
                handle.write(b"source")
            job = metaclean.new_job("clean", 1)
            fake_result = {"rel": "photo.jpg", "status": "ok", "dest": output, "notes": []}
            with patch.object(metaclean, "tools", return_value={}), \
                 patch.object(metaclean, "clean_one", return_value=fake_result), \
                 patch.object(metaclean, "resolve", return_value=original), \
                 patch.object(metaclean, "media_scan"):
                metaclean.run_clean_job(job, ["photo.jpg"], "copy", "auto", False, True)
            self.assertFalse(os.path.exists(original))
            self.assertTrue(job["results"][0]["original_deleted"])

    def test_failed_clean_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder:
            original = os.path.join(folder, "photo.jpg")
            with open(original, "wb") as handle:
                handle.write(b"source")
            job = metaclean.new_job("clean", 1)
            with patch.object(metaclean, "tools", return_value={}), \
                 patch.object(metaclean, "clean_one", side_effect=metaclean.ToolError("test failure")), \
                 patch.object(metaclean, "media_scan"):
                metaclean.run_clean_job(job, ["photo.jpg"], "copy", "auto", False, True)
            self.assertTrue(os.path.exists(original))
            self.assertFalse(job["results"][0].get("original_deleted", False))

    def test_run_all_passes_delete_original_preference(self):
        previous_items = metaclean.INDEX["items"]
        job = metaclean.new_job("run-all")
        scan = {"status": "done", "message": "", "id": "scan-test"}
        metaclean.INDEX["items"] = {
            "DCIM/photo.jpg": {
                "rel": "DCIM/photo.jpg", "supported": True, "cleaned": False
            }
        }
        try:
            with patch.object(metaclean, "new_job", return_value=scan), \
                 patch.object(metaclean, "run_scan_job", side_effect=lambda scan_job, hidden: scan_job.update(status="done")), \
                 patch.object(metaclean.os.path, "exists", return_value=False), \
                 patch.object(metaclean, "run_clean_job") as clean:
                metaclean.run_all_job(job, False, False, True)
            clean.assert_called_once_with(
                job, ["DCIM/photo.jpg"], "copy", "auto", False, True
            )
        finally:
            metaclean.INDEX["items"] = previous_items


if __name__ == "__main__":
    unittest.main()

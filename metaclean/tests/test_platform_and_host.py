import os
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()

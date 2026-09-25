"""Unit tests for models management, categorization, health checks, and providers."""

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from model_checker import check_single_model_health
from models import (
    ModelInfo,
    detect_categories,
    detect_invocation_type,
    hide_non_working_models,
    load_model_statuses,
    unhide_all_models,
    update_model_status,
)
from providers import ProviderConfig


class TestModelsCategorization(unittest.TestCase):

    def test_detect_categories_code(self):
        cats = detect_categories("claude-3-5-sonnet", "Claude 3.5 Sonnet")
        self.assertIn("code", cats)
        self.assertIn("text", cats)

    def test_detect_categories_image(self):
        cats = detect_categories("dall-e-3", "DALL-E 3")
        self.assertIn("image", cats)

    def test_detect_categories_video(self):
        cats = detect_categories("sora-v1", "OpenAI Sora")
        self.assertIn("video", cats)

    def test_detect_categories_audio(self):
        cats = detect_categories("whisper-large-v3", "Whisper Speech to Text")
        self.assertIn("audio", cats)

    def test_detect_invocation_type(self):
        inv_claude = detect_invocation_type("claude-3-opus")
        self.assertEqual(inv_claude, "claude_code")

        inv_gpt = detect_invocation_type("gpt-4o")
        self.assertEqual(inv_gpt, "opencode")

    def test_model_info_class(self):
        info = ModelInfo("gpt-4o", label="GPT-4 Omni")
        self.assertIn("text", info.categories)
        self.assertEqual(info.invocation_type, "opencode")
        self.assertIn("💬", info.get_category_emojis())
        self.assertEqual(info.get_invocation_emoji(), "⚡")


class TestModelStatusManagement(unittest.TestCase):

    def setUp(self):
        self.test_status_file = Path("data/test_model_status.json")
        self.patcher = patch("models.MODEL_STATUS_FILE", self.test_status_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if self.test_status_file.exists():
            self.test_status_file.unlink()

    def test_update_and_load_status(self):
        update_model_status("test-model-1", "working")
        statuses = load_model_statuses()
        self.assertIn("test-model-1", statuses)
        self.assertEqual(statuses["test-model-1"]["status"], "working")

        update_model_status("test-model-2", "non_working", error_message="HTTP 500", hide_if_failed=True)
        statuses = load_model_statuses()
        self.assertEqual(statuses["test-model-2"]["status"], "hidden")
        self.assertEqual(statuses["test-model-2"]["error_message"], "HTTP 500")

    def test_hide_and_unhide_models(self):
        update_model_status("m1", "non_working")
        update_model_status("m2", "working")

        hidden_cnt = hide_non_working_models(["m1", "m2"])
        self.assertEqual(hidden_cnt, 1)

        statuses = load_model_statuses()
        self.assertEqual(statuses["m1"]["status"], "hidden")

        unhide_cnt = unhide_all_models()
        self.assertEqual(unhide_cnt, 1)

        statuses = load_model_statuses()
        self.assertEqual(statuses["m1"]["status"], "unknown")


class TestProviderConfigFiltering(unittest.TestCase):

    def setUp(self):
        self.test_status_file = Path("data/test_model_status_provider.json")
        self.patcher = patch("models.MODEL_STATUS_FILE", self.test_status_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if self.test_status_file.exists():
            self.test_status_file.unlink()

    def test_get_model_list_filtering(self):
        provider = ProviderConfig("test_prov", {
            "models": [
                {"id": "claude-3-sonnet", "label": "Claude 3 Sonnet"},
                {"id": "dall-e-3", "label": "DALL-E 3"},
                {"id": "broken-model", "label": "Broken Model"},
            ]
        })

        update_model_status("broken-model", "hidden")

        # Hidden ausgeblendet
        active_models = provider.get_model_list(include_hidden=False)
        model_ids = [m[0] for m in active_models]
        self.assertIn("claude-3-sonnet", model_ids)
        self.assertIn("dall-e-3", model_ids)
        self.assertNotIn("broken-model", model_ids)

        # Kategorie-Filter (image)
        image_models = provider.get_model_list(include_hidden=False, category="image")
        img_ids = [m[0] for m in image_models]
        self.assertIn("dall-e-3", img_ids)
        self.assertNotIn("claude-3-sonnet", img_ids)


class TestModelChecker(unittest.IsolatedAsyncioTestCase):

    async def test_check_single_model_health_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            is_working, err = await check_single_model_health("http://fake.api", "key", "gpt-4")
            self.assertTrue(is_working)
            self.assertIsNone(err)

    async def test_check_single_model_health_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Model not found"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            is_working, err = await check_single_model_health("http://fake.api", "key", "invalid-model")
            self.assertFalse(is_working)
            self.assertIn("404", err)


if __name__ == "__main__":
    unittest.main()

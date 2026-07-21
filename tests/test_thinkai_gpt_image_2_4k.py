import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "xiaohongshu-content-employee"
IMAGE_SCRIPT_DIR = PLUGIN_ROOT / "scripts" / "生图工具"
sys.path.insert(0, str(IMAGE_SCRIPT_DIR))

import configure_provider  # noqa: E402
import generate_image  # noqa: E402
import provider_registry  # noqa: E402
from providers import get_adapter  # noqa: E402


class ThinkAiGptImage24kTests(unittest.TestCase):
    def test_registers_and_configures_gpt_image_2_4k(self):
        provider_id = "thinkai-gpt-image-2-4k"
        provider = provider_registry.get_provider(provider_id)

        self.assertEqual(provider["adapter"], "thinkai")
        self.assertEqual(provider["base_url"], "https://www.thinkai.tv/v1")
        self.assertEqual(provider["models"]["recommended"], "gpt-image-2-4k")
        self.assertEqual(provider["default_size"], "1536x2048")

        with tempfile.TemporaryDirectory() as temporary:
            skill_root = Path(temporary)
            configure_provider.save_formal_provider_config(
                skill_root,
                provider_id,
                "test-key",
            )
            saved = json.loads((skill_root / "config.json").read_text("utf-8"))

        self.assertEqual(saved["default_provider"], provider_id)
        self.assertEqual(
            saved["providers"][provider_id],
            {"api_key": "test-key", "model_alias": "recommended"},
        )

        config = get_adapter(provider_id).load_config(saved, provider)
        request = get_adapter(provider_id).build_request(
            config,
            "vertical product image",
            "1536x2048",
            "hd",
        )
        self.assertEqual(request["url"], "https://www.thinkai.tv/v1/images/generations")
        self.assertEqual(request["body"]["model"], "gpt-image-2-4k")
        self.assertEqual(request["body"]["size"], "1536x2048")
        self.assertEqual(request["body"]["quality"], "hd")

    def test_load_provider_uses_saved_gpt_image_2_4k_configuration(self):
        provider_id = "thinkai-gpt-image-2-4k"
        with tempfile.TemporaryDirectory() as temporary:
            skill_root = Path(temporary)
            configure_provider.save_formal_provider_config(
                skill_root,
                provider_id,
                "test-key",
            )
            resolved_id, adapter, config, provider = generate_image.load_provider(
                skill_root,
            )

        self.assertEqual(resolved_id, provider_id)
        self.assertEqual(config["model"], "gpt-image-2-4k")
        self.assertEqual(adapter.normalize_size(None, provider), "1536x2048")

    def test_custom_ratio_sizes_resolve_to_requested_1k_and_2k_dimensions(self):
        adapter = get_adapter("thinkai-gpt-image-2-4k")
        provider = provider_registry.get_provider("thinkai-gpt-image-2-4k")

        self.assertEqual(adapter.normalize_size("16:9@1k", provider), "1920x1080")
        self.assertEqual(adapter.normalize_size("4:3@2k", provider), "2560x1920")
        self.assertEqual(adapter.normalize_size("1:1@1k", provider), "1920x1920")

    def test_resolve_request_size_uses_explicit_thinkai_4k_size(self):
        provider_id = "thinkai-gpt-image-2-4k"
        adapter = get_adapter(provider_id)
        provider = provider_registry.get_provider(provider_id)

        size = generate_image.resolve_request_size(
            provider_id,
            adapter,
            {"default_size": "1536x2048"},
            provider,
            "16:9@1k",
        )

        self.assertEqual(size, "1920x1080")

    def test_reference_images_use_thinkai_edits_multipart_request(self):
        provider_id = "thinkai-gpt-image-2-4k"
        provider = provider_registry.get_provider(provider_id)
        config = get_adapter(provider_id).load_config(
            {
                "providers": {
                    provider_id: {
                        "api_key": "test-key",
                        "model_alias": "recommended",
                    }
                }
            },
            provider,
        )

        with tempfile.TemporaryDirectory() as temporary:
            reference_image = Path(temporary) / "reference.jpg"
            reference_image.write_bytes(b"jpeg-bytes")
            request = generate_image.build_request(
                provider_id,
                get_adapter(provider_id),
                config,
                "use the supplied product image",
                "1920x1080",
                [reference_image],
            )

        self.assertEqual(request["url"], "https://www.thinkai.tv/v1/images/edits")
        self.assertEqual(request["data"]["model"], "gpt-image-2-4k")
        self.assertEqual(request["data"]["size"], "1920x1080")
        self.assertEqual(
            request["files"],
            [("image[]", ("reference.jpg", b"jpeg-bytes", "image/jpeg"))],
        )
        self.assertNotIn("Content-Type", request["headers"])


if __name__ == "__main__":
    unittest.main()

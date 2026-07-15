"""图片生成渠道适配器。"""

from providers import (
    custom,
    google_image,
    openai_image,
    thinkai,
    thinkai_nano,
    volcengine,
)


SUPPORTED_PROVIDERS = (
    "thinkai-image-2",
    "thinkai-nano",
    "seedream",
    "openai-gpt-image",
    "google-nano-banana",
    "custom",
)


def get_adapter(provider_id: str):
    normalized = str(provider_id or "").strip().lower()
    if normalized.startswith("custom-"):
        normalized = "custom"
    adapters = {
        "thinkai": thinkai,
        "thinkai-image2": thinkai,
        "thinkai-image-2": thinkai,
        "thinkai-nano": thinkai_nano,
        "volcengine": volcengine,
        "seedream": volcengine,
        "openai": openai_image,
        "openai-gpt-image": openai_image,
        "google": google_image,
        "google-nano-banana": google_image,
        "custom": custom,
    }
    adapter = adapters.get(normalized)
    if adapter is None:
        raise RuntimeError(f"不支持的图片渠道：{provider_id}")
    return adapter

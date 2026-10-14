from __future__ import annotations

import pytest

from app.llm import configured_models


def test_group_connection_supplies_shared_credentials_without_changing_model_identity(monkeypatch) -> None:
    monkeypatch.setattr(configured_models, "decrypt_secret", lambda value: {"group-key": "secret"}[value])
    instance = {
        "_id": "member-1", "main_id": "tenant-a", "provider_id": "provider-1",
        "display_name": "Text model", "model_name": "gpt-example", "status": "active",
        "capabilities": ["chat"], "api_key_encrypted": "", "base_url": "",
    }
    provider = {"name": "OpenAI", "code": "openai", "provider_type": "openai_compatible"}
    group = {"status": "active", "api_key_encrypted": "group-key", "base_url": "https://example.invalid/v1"}

    config = configured_models._to_runtime_config(instance, provider, group=group)

    assert config["id"] == "member-1"
    assert config["model_name"] == "gpt-example"
    assert config["api_key"] == "secret"
    assert config["base_url"] == "https://example.invalid/v1"


def test_disabled_group_cannot_supply_credentials() -> None:
    with pytest.raises(configured_models.ModelConfigError, match="模型组已禁用"):
        configured_models._to_runtime_config(
            {"status": "active", "capabilities": ["chat"]}, {},
            group={"status": "disabled"},
        )


def test_image_member_uses_own_runtime_settings_and_group_connection(monkeypatch) -> None:
    monkeypatch.setattr(configured_models, "decrypt_secret", lambda value: "secret" if value == "group-key" else "")
    config = configured_models._to_runtime_config(
        {
            "_id": "image-member", "model_name": "image-v2", "status": "active",
            "capabilities": ["image_generation"], "runtime_kind": "openai_images",
            "settings": {"size": "1024x1024"},
        },
        {"provider_type": "openai_compatible", "name": "OpenAI"},
        group={"status": "active", "api_key_encrypted": "group-key", "base_url": "https://shared.example/v1"},
        required_capability="image_generation",
    )

    assert config["model_name"] == "image-v2"
    assert config["runtime_kind"] == "openai_images"
    assert config["settings"] == {"size": "1024x1024"}
    assert config["base_url"] == "https://shared.example/v1"

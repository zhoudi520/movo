from app.token_usage.model_identity import usage_model_id


def test_configured_instance_id_wins_over_provider_deployment_name() -> None:
    assert usage_model_id("configured-instance-1", {"model_id": "deepseek-v4-flash"}) == "configured-instance-1"


def test_unconfigured_client_uses_provider_identity() -> None:
    assert usage_model_id("", {"model_id": "deepseek-v4-flash"}) == "deepseek-v4-flash"

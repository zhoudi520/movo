import asyncio
from decimal import Decimal

import pytest

from app.services.model_pricing import calculate_cost, load_model_prices, normalize_pricing, serialize_costs


def test_price_uses_configured_currency_and_separate_input_output_rates() -> None:
    pricing = normalize_pricing({"currency": "USD", "inputPerMillion": 2, "outputPerMillion": 8})
    assert pricing == {"currency": "USD", "inputPerMillion": "2", "outputPerMillion": "8"}
    result = calculate_cost(
        {"model_id": "model-a", "model_name": "same-name", "prompt_tokens": 500000, "completion_tokens": 250000},
        ({"model-a": pricing}, {}),
    )
    assert result == ("USD", Decimal("3"))
    assert serialize_costs({"USD": result[1]}) == {"CNY": 0.0, "USD": 3.0}


@pytest.mark.parametrize("value", [
    {"currency": "EUR", "inputPerMillion": 1, "outputPerMillion": 2},
    {"currency": "CNY", "inputPerMillion": -1, "outputPerMillion": 2},
    {"currency": "CNY", "inputPerMillion": "NaN", "outputPerMillion": 2},
])
def test_invalid_price_is_rejected(value: dict) -> None:
    with pytest.raises(ValueError):
        normalize_pricing(value)


def test_unconfigured_model_has_no_invented_cost() -> None:
    assert calculate_cost({"model_name": "unknown", "prompt_tokens": 100}, ({}, {})) is None


def test_equal_prices_keep_legacy_name_fallback() -> None:
    class Cursor:
        async def to_list(self, length: int):
            return [
                {"_id": "group-model", "model_name": "deepseek-v4-flash", "pricing": {"currency": "CNY", "inputPerMillion": "2", "outputPerMillion": "8"}},
                {"_id": "single-model", "model_name": "deepseek-v4-flash", "pricing": {"currency": "CNY", "inputPerMillion": "2.0", "outputPerMillion": "8.00"}},
            ]

    class Collection:
        def find(self, query, projection):
            return Cursor()

    prices = asyncio.run(load_model_prices({"admin_model_instances": Collection()}, "tenant-a"))
    assert calculate_cost({"model_id": "deepseek-v4-flash", "model_name": "deepseek-v4-flash", "prompt_tokens": 1000000}, prices) == ("CNY", Decimal("2"))


def test_different_prices_require_instance_id() -> None:
    class Cursor:
        async def to_list(self, length: int):
            return [
                {"_id": "group-model", "model_name": "same-name", "pricing": {"currency": "CNY", "inputPerMillion": "2", "outputPerMillion": "8"}},
                {"_id": "single-model", "model_name": "same-name", "pricing": {"currency": "CNY", "inputPerMillion": "3", "outputPerMillion": "8"}},
            ]

    class Collection:
        def find(self, query, projection):
            return Cursor()

    prices = asyncio.run(load_model_prices({"admin_model_instances": Collection()}, "tenant-a"))
    assert calculate_cost({"model_id": "group-model", "model_name": "same-name", "prompt_tokens": 1000000}, prices) == ("CNY", Decimal("2"))
    assert calculate_cost({"model_id": "same-name", "model_name": "same-name", "prompt_tokens": 1000000}, prices) is None

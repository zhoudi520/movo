from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.repositories.model_repository import INSTANCE_COLLECTION

CURRENCIES = ("CNY", "USD")


def _same_price(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["currency"] == right["currency"] and all(
        Decimal(left[key]) == Decimal(right[key]) for key in ("inputPerMillion", "outputPerMillion")
    )


def normalize_pricing(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("pricing_invalid")
    currency = str(value.get("currency") or "").upper()
    if currency not in CURRENCIES:
        raise ValueError("pricing_currency_invalid")
    result: dict[str, Any] = {"currency": currency}
    for key in ("inputPerMillion", "outputPerMillion"):
        try:
            amount = Decimal(str(value.get(key)))
        except (InvalidOperation, TypeError):
            raise ValueError("pricing_amount_invalid") from None
        if not amount.is_finite() or amount < 0 or amount > 1000000:
            raise ValueError("pricing_amount_invalid")
        result[key] = str(amount)
    return result


async def load_model_prices(db: Any, main_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    docs = await db[INSTANCE_COLLECTION].find(
        {"main_id": main_id}, {"model_name": 1, "pricing": 1}
    ).to_list(length=5000)
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    ambiguous_names: set[str] = set()
    for doc in docs:
        try:
            price = normalize_pricing(doc.get("pricing"))
        except ValueError:
            continue
        if price is None:
            continue
        by_id[str(doc["_id"])] = price
        name = str(doc.get("model_name") or "")
        if name in by_name and not _same_price(by_name[name], price):
            ambiguous_names.add(name)
        elif name not in by_name:
            by_name[name] = price
    for name in ambiguous_names:
        by_name.pop(name, None)
    return by_id, by_name


def calculate_cost(row: dict[str, Any], prices: tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]) -> tuple[str, Decimal] | None:
    by_id, by_name = prices
    price = by_id.get(str(row.get("model_id") or "")) or by_name.get(str(row.get("model_name") or ""))
    if price is None:
        return None
    prompt = Decimal(int(row.get("prompt_tokens") or 0))
    completion = Decimal(int(row.get("completion_tokens") or 0))
    amount = (prompt * Decimal(price["inputPerMillion"]) + completion * Decimal(price["outputPerMillion"])) / Decimal(1000000)
    return price["currency"], amount


def serialize_costs(totals: dict[str, Decimal]) -> dict[str, float]:
    return {currency: float(totals.get(currency, Decimal(0)).quantize(Decimal("0.00000001"))) for currency in CURRENCIES}

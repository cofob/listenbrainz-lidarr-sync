from __future__ import annotations

from collections.abc import Sequence

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
type JsonMapping = dict[str, JsonValue]


class PayloadError(ValueError):
    """Raised when an upstream API response does not match the expected shape."""


def as_mapping(value: JsonValue, context: str) -> JsonMapping:
    if not isinstance(value, dict):
        raise PayloadError(f"Expected {context} to be an object.")
    return value


def maybe_mapping(value: JsonValue | None) -> JsonMapping | None:
    if isinstance(value, dict):
        return value
    return None


def as_list(value: JsonValue | None) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    return []


def as_str(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def as_int(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def as_bool(value: JsonValue | None) -> bool:
    return value if isinstance(value, bool) else False


def string_values(value: JsonValue | None) -> Sequence[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []

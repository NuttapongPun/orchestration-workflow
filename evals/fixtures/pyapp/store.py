"""In-memory item store, seeded once from data/items.json."""
import json
import pathlib

_DATA = pathlib.Path(__file__).parent / "data" / "items.json"
_items: dict[str, dict] = {}


def load() -> None:
    _items.clear()
    for item in json.loads(_DATA.read_text()):
        _items[item["id"]] = item


def get(item_id: str) -> dict | None:
    return _items.get(item_id)


def put(item: dict) -> None:
    _items[item["id"]] = item


def all_items() -> list[dict]:
    return list(_items.values())

"""Static file helper for the planned /static endpoint."""
import pathlib

STATIC = pathlib.Path(__file__).parent / "static"


def read_static(name: str) -> bytes:
    return (STATIC / name).read_bytes()

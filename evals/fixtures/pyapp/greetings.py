"""Greeting helpers. Each language has one function with the same shape."""


def greet_en(name: str) -> str:
    return f"Hello, {name}!"


def greet_fr(name: str) -> str:
    return f"Bonjour, {name} !"


def greet_es(name: str) -> str:
    return f"¡Hola, {name}!"


GREETERS = {
    "en": greet_en,
    "fr": greet_fr,
    "es": greet_es,
}


def greet(name: str, lang: str = "en") -> str:
    return GREETERS.get(lang, greet_en)(name)

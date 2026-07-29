from __future__ import annotations

import re


def normalize_lexical_text(text: str, language: str = "und") -> str:
    normalized = text.casefold()
    if language.startswith("zh") or re.search(r"[\u3400-\u9fff]", normalized):
        tokens = re.findall(r"[\u3400-\u9fff]|[a-z0-9_-]+", normalized)
        return " ".join(tokens)
    return " ".join(re.findall(r"[a-z0-9_-]+", normalized))

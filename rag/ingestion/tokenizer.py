from __future__ import annotations

import re

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None


class TokenCounter:
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self.encoding = tiktoken.get_encoding(encoding_name) if tiktoken is not None else None

    def encode(self, text: str) -> list[int] | list[str]:
        if self.encoding is not None:
            return self.encoding.encode(text)
        return re.findall(r"[\u3400-\u9fff]|\w+|[^\w\s]", text, flags=re.UNICODE)

    def decode(self, tokens: list[int] | list[str]) -> str:
        if self.encoding is not None:
            return self.encoding.decode(tokens)  # type: ignore[arg-type]
        return "".join(tokens)  # type: ignore[arg-type]

    def count(self, text: str) -> int:
        return len(self.encode(text))

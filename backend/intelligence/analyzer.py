import json
import os
from collections import Counter
from typing import Any

import requests


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
OPENAI_URL = "https://api.openai.com/v1/responses"


def _text(value: Any, limit: int = 4000) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _unique(items):
    seen = set()
    result = []

    for item in items:
        key = (
            item.get("url")
            or item.get("id")
            or item.get("title")
            or ""
        )

        if key and key not in seen:
            seen.add(key)
            result.append(item)

    return result


def _build_source_text(items, limit=80):
    blocks = []

    for i, item in enumerate(items[:limit], 1):
        blocks.append(
            f"""
SOURCE {i}
Type: {item.get("type", "")}
Source: {item.get("source", "")}
Author: {item.get("author", "")}
Published: {item.get("published", "")}
Title: {_text(item.get("title"), 500)}
Content/Snippet: {_text(item.get("snippet"), 1800)}
URL: {item.get("url", "")}
"""
        )

    return "\n".join(blocks)


SYSTEM_PROMPT = """
Du är TradePilot Intelligence.

Din uppgift är att analysera marknadsinformation och upptäcka
INVESTERINGSRELEVANTA HÄNDELSER och STORYS.

Du ska INTE automatiskt rekommendera köp.

Du ska försöka upptäcka sådant som marknaden kanske ännu inte
har förstått fullt ut.

Viktiga exempel:

- företag i finansi

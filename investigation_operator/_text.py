"""Keyword overlap, for matching text a model wrote twice in different words.
Used to match SOP steps back to video rows, and tasks in one SOP to the other.
"""

import re

STOPWORDS = set("the a an of to in on at for and or from into with".split())


def keywords(text: str, min_len: int = 2) -> set[str]:
    """Content words in `text`, lowercased, longer than `min_len`."""
    return {w for w in re.findall(r"[a-z]+", text.lower())
            if w not in STOPWORDS and len(w) > min_len}


def overlap(a: str, b: str, min_len: int = 2) -> float:
    """Share of keywords two texts have in common, 0.0 if either has none."""
    ka, kb = keywords(a, min_len), keywords(b, min_len)
    union = ka | kb
    return len(ka & kb) / len(union) if union else 0.0

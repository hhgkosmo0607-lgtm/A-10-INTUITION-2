"""Pull checkable values (money, percent, counts) out of Korean text and normalise them."""

import re
from dataclasses import dataclass

from factlock.domain.models import Value

_UNIT_ALIASES = {"곳": "개", "개사": "개", "군데": "개", "개소": "개", "유저": "USER", "user": "USER"}
_COUNT_UNITS = ("개사", "개소", "군데", "USER", "user", "유저", "개", "석", "건", "명", "곳", "대", "회")
_SCALE = {"만": 10_000, "천": 1_000, "억": 100_000_000}

_MONEY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|만|천)?\s*원")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_COUNT = re.compile(r"(\d[\d,]*)\s*(?:여\s*)?(" + "|".join(_COUNT_UNITS) + r")(?!월)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_SPACE = re.compile(r"\s+")

# Counts below this are too common in prose ("3단계", "2명이") to check against the fact list.
MIN_CHECKED_COUNT = 10


@dataclass(frozen=True)
class Found:
    value: Value
    text: str
    start: int


def _number(raw: str) -> float:
    return float(raw.replace(",", ""))


def extract_values(text: str) -> list[Found]:
    """Return money, percent and count values in reading order. Dates and list numbers are skipped."""
    found: list[Found] = []
    taken: list[tuple[int, int]] = []
    for match in _MONEY.finditer(text):
        amount = round(_number(match.group(1)) * _SCALE.get(match.group(2) or "", 1))
        found.append(Found(Value(amount, "원"), match.group(0), match.start()))
        taken.append(match.span())
    for match in _PERCENT.finditer(text):
        found.append(Found(Value(round(_number(match.group(1)) * 10), "‰"), match.group(0), match.start()))
    for match in _COUNT.finditer(text):
        if any(start <= match.start() < end for start, end in taken):
            continue
        unit = _UNIT_ALIASES.get(match.group(2), match.group(2))
        found.append(Found(Value(round(_number(match.group(1))), unit), match.group(0), match.start()))
    return sorted(found, key=lambda item: item.start)


def is_checked(value: Value) -> bool:
    """Money and percent are always checked; small counts are left alone."""
    return value.unit in ("원", "‰") or value.amount >= MIN_CHECKED_COUNT


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def squash(text: str) -> str:
    """Lower-case and drop whitespace so '콜센터 프로그램' matches '콜센터프로그램'."""
    return _SPACE.sub("", text).lower()


def contains(text: str, term: str) -> bool:
    return squash(term) in squash(text)

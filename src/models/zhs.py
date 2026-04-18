"""Pydantic models for ZHS sport courses."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

_CATEGORY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"yoga|yogilates|acroyoga|pilates", re.I), "Yoga & Mindfulness"),
    (re.compile(r"climb|boulder|klettern", re.I), "Climbing & Bouldering"),
    (
        re.compile(r"sail|segel|windsurf|kitesurf|wing.?surf|sup\b|canoe|kanu|row", re.I),
        "Water Sports",
    ),
    (
        re.compile(r"swim|schwimm|aqua|synchron|diving|tauch|water jump", re.I),
        "Swimming & Aquatics",
    ),
    (re.compile(r"surf(?!.*wind)(?!.*wing)", re.I), "Water Sports"),
    (
        re.compile(
            r"dance|danc|tango|bachata|swing|standard.*latin|latin.*dance|afro|amapiano|contemporary",
            re.I,
        ),
        "Dance",
    ),
    (re.compile(r"run|lauf|trail|marathon|orienteer|endurance", re.I), "Running & Endurance"),
    (
        re.compile(
            r"fitness|hiit|body pump|zumba|step|condition|indoor.?cycl"
            r"|circuit|strength|kraft|r.cken",
            re.I,
        ),
        "Fitness & Training",
    ),
    (re.compile(r"football|fu.ball|soccer|futsal|beach.?soccer", re.I), "Football"),
    (re.compile(r"volleyball|beachvolley", re.I), "Volleyball"),
    (re.compile(r"tennis|pickleball|beachtennis", re.I), "Racket Sports"),
    (
        re.compile(
            r"basketball|hockey|baseball|handball|table tennis|tischtennis|chess|schach", re.I
        ),
        "Ball & Table Sports",
    ),
    (re.compile(r"judo|tae kwon|martial|kampf", re.I), "Martial Arts"),
    (
        re.compile(r"mountain|berg|alpin|hochtouren|via ferrata|hiking|wander", re.I),
        "Mountaineering & Hiking",
    ),
    (re.compile(r"bike|mountain.?bike|longboard", re.I), "Cycling"),
    (re.compile(r"golf", re.I), "Golf"),
    (re.compile(r"acrobat|gymnast|turnen", re.I), "Gymnastics"),
]

_LEVEL_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"begin|einstieg|einstiegs|lernen|learn|intro|einf.hrung|taster|schnupper", re.I
        ),
        "Beginner",
    ),
    (
        re.compile(r"fortgeschritt|intermedia|advanced|verbesser|improv|technique|technik", re.I),
        "Intermediate",
    ),
    (
        re.compile(
            r"leistung|performance|ausbildung|education|license|lizenz|training\s+SKS", re.I
        ),
        "Advanced",
    ),
]

_LOCATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"freising|weihenstephan", re.I), "Freising"),
    (re.compile(r"garching", re.I), "Garching"),
    (re.compile(r"landshut", re.I), "Landshut"),
    (re.compile(r"triesdorf", re.I), "Triesdorf"),
]


def _infer_category(name: str, description: str) -> str:
    text = f"{name} {description}"
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(text):
            return category
    return "Other"


def _infer_level(name: str) -> str:
    for pattern, level in _LEVEL_RULES:
        if pattern.search(name):
            return level
    return "All Levels"


def _infer_location(name: str) -> str:
    for pattern, location in _LOCATION_PATTERNS:
        if pattern.search(name):
            return location
    return "Munich"


CATEGORY_EMOJI: dict[str, str] = {
    "Yoga & Mindfulness": "\U0001f9d8",
    "Climbing & Bouldering": "\U0001f9d7",
    "Water Sports": "\U0001f3c4",
    "Swimming & Aquatics": "\U0001f3ca",
    "Dance": "\U0001f483",
    "Running & Endurance": "\U0001f3c3",
    "Fitness & Training": "\U0001f4aa",
    "Football": "\u26bd",
    "Volleyball": "\U0001f3d0",
    "Racket Sports": "\U0001f3be",
    "Ball & Table Sports": "\U0001f3c0",
    "Martial Arts": "\U0001f94b",
    "Mountaineering & Hiking": "\u26f0\ufe0f",
    "Cycling": "\U0001f6b5",
    "Golf": "\u26f3",
    "Gymnastics": "\U0001f938",
    "Other": "\U0001f3c5",
}


class ZhsCourse(BaseModel):
    """A sport course/offer from ZHS Munich."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    name_de: str = ""
    description_short: str = ""
    slug: str = ""
    group_id: str = ""
    url: str = ""
    poster_url: str = ""
    category: str = "Other"
    level: str = "All Levels"
    location: str = "Munich"

    def to_tool_dict(self) -> dict[str, object]:
        """Flat dict for LLM tool consumption."""
        return {
            "id": self.id,
            "name": self.name,
            "name_de": self.name_de,
            "description": self.description_short,
            "url": self.url,
            "poster_url": self.poster_url,
            "category": self.category,
            "emoji": CATEGORY_EMOJI.get(self.category, "\U0001f3c5"),
            "level": self.level,
            "location": self.location,
        }

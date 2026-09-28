"""Conservative text-only prompts for an offline visual perception baseline.

Only the task sentence is accepted. Unsupported syntax or two distinct phrases
with the same head noun fail explicitly; this is not a general LIBERO parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_COMMAND = re.compile(
    r"^(?:pick up|pick|grab|take) (?:the|a|an) (?P<target>.+?) "
    r"and (?:then )?(?:place|put) it (?P<goal>.+)$"
)
_BETWEEN = re.compile(
    r"^(?P<object>.+?) between (?:the|a|an) (?P<ref_a>.+?) "
    r"and (?:the|a|an) (?P<ref_b>.+)$"
)
_GOAL = re.compile(r"^(?P<relation>on|onto|in|into|inside) (?:the|a|an) (?P<object>.+)$")
_PHRASE = re.compile(r"^[a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)*$")
_UNSUPPORTED_PHRASE_WORDS = frozenset({
    "between", "not", "next", "left", "right", "front", "back", "middle", "center",
    "centre", "of", "on", "in", "under", "behind", "above", "below", "near",
})


@dataclass(frozen=True)
class VisualPickPlaceLanguage:
    target_phrase: str
    reference_phrases: tuple[str, ...]
    goal_phrase: str
    goal_relation: str


def category_for_phrase(phrase: str) -> str:
    if _PHRASE.fullmatch(phrase) is None or _UNSUPPORTED_PHRASE_WORDS.intersection(phrase.split()):
        raise ValueError(f"unsupported object phrase: {phrase!r}")
    return phrase.rsplit(" ", 1)[-1]


def parse_visual_pick_place_language(language: str) -> VisualPickPlaceLanguage:
    """Parse only the supported pick/place sentence form, without a scene."""

    text = " ".join(str(language).lower().strip().rstrip(".").split())
    command = _COMMAND.fullmatch(text)
    if command is None:
        raise ValueError("unsupported task language: expected pick/place with an object goal")
    target = command.group("target")
    between = _BETWEEN.fullmatch(target)
    goal = _GOAL.fullmatch(command.group("goal"))
    if goal is None:
        raise ValueError("unsupported visual goal: expected on/in followed by an object")
    target_phrase = between.group("object") if between is not None else target
    references = (between.group("ref_a"), between.group("ref_b")) if between is not None else ()
    goal_phrase = goal.group("object")
    for phrase in (target_phrase, *references, goal_phrase):
        category_for_phrase(phrase)
    return VisualPickPlaceLanguage(
        target_phrase=target_phrase,
        reference_phrases=references,
        goal_phrase=goal_phrase,
        goal_relation="on" if goal.group("relation") in ("on", "onto") else "inside",
    )


def prompts_from_task_language(language: str) -> dict[str, str]:
    """Extract target, reference and goal prompts from the task sentence.

    The dictionary key is the final noun token used by the detector as a broad
    category. A descriptive phrase such as ``black bowl`` remains the prompt.
    Its adjective is detector input, not verified object identity evidence.
    """

    task = parse_visual_pick_place_language(language)
    prompts: dict[str, str] = {}
    for phrase in (task.target_phrase, *task.reference_phrases, task.goal_phrase):
        category = category_for_phrase(phrase)
        prior = prompts.get(category)
        if prior is not None and prior != phrase:
            raise ValueError(f"conflicting descriptions for category {category!r}: {prior!r}, {phrase!r}")
        prompts[category] = phrase
    return prompts

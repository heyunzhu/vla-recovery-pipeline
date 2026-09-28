"""Conservative text-only prompts for an offline visual perception baseline.

Only the task sentence is accepted. Unsupported syntax or two distinct phrases
with the same head noun fail explicitly; this is not a general LIBERO parser.
"""

from __future__ import annotations

import re


_COMMAND = re.compile(
    r"^(?:pick up|pick|grab|take) (?:the|a|an) (?P<target>.+?) "
    r"and (?:then )?(?:place|put) it (?P<goal>.+)$"
)
_BETWEEN = re.compile(
    r"^(?P<object>.+?) between (?:the|a|an) (?P<ref_a>.+?) "
    r"and (?:the|a|an) (?P<ref_b>.+)$"
)
_GOAL = re.compile(r"^(?:on|onto|in|into|inside) (?:the|a|an) (?P<object>.+)$")
_PHRASE = re.compile(r"^[a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)*$")


def prompts_from_task_language(language: str) -> dict[str, str]:
    """Extract target, reference and goal phrases from a supported sentence.

    The dictionary key is the final noun token used by the detector as a broad
    category. A descriptive phrase such as ``black bowl`` remains the prompt.
    Its adjective is detector input, not verified object identity evidence.
    """

    text = " ".join(str(language).lower().strip().rstrip(".").split())
    command = _COMMAND.fullmatch(text)
    if command is None:
        raise ValueError("unsupported task language: expected pick/place with an object goal")
    target = command.group("target")
    between = _BETWEEN.fullmatch(target)
    phrases = (
        [between.group("object"), between.group("ref_a"), between.group("ref_b")]
        if between is not None else [target]
    )
    goal = _GOAL.fullmatch(command.group("goal"))
    if goal is None:
        raise ValueError("unsupported visual goal: expected on/in followed by an object")
    phrases.append(goal.group("object"))

    prompts: dict[str, str] = {}
    for phrase in phrases:
        if _PHRASE.fullmatch(phrase) is None:
            raise ValueError(f"unsupported object phrase: {phrase!r}")
        category = phrase.rsplit(" ", 1)[-1]
        prior = prompts.get(category)
        if prior is not None and prior != phrase:
            raise ValueError(f"conflicting descriptions for category {category!r}: {prior!r}, {phrase!r}")
        prompts[category] = phrase
    return prompts

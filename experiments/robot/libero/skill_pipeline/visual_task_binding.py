"""Offline, visual-only ID binding for a narrow pick/place language subset.

This binds observed scene IDs, not grasp or placement geometry. It never reads
MuJoCo, BDDL, contacts, named sites, or an evaluation success signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .rgbd_scene import VisualObject, VisualSceneSnapshot
from .visual_language_prompts import category_for_phrase, parse_visual_pick_place_language


@dataclass(frozen=True)
class VisualTaskBinding:
    snapshot_id: str
    source: str = "task_language_rgbd_scene"
    status: str = "refused"
    reason: str | None = None
    target_id: str | None = None
    goal_id: str | None = None
    reference_ids: tuple[str, ...] = ()
    goal_relation: str | None = None
    unverified_descriptors: tuple[str, ...] = ()
    evidence: dict[str, object] = field(default_factory=dict)


def _eligible(scene: VisualSceneSnapshot, category: str) -> list[VisualObject]:
    return [
        item for item in scene.objects
        if item.category == category
        and item.validity == "observed"
        and item.identity_status in ("new", "tracked")
        and item.id.startswith("obj_")
        and item.visible_centroid_world_m is not None
    ]


def _between_measurement(target: VisualObject, first: VisualObject, second: VisualObject) -> dict[str, object]:
    first_xy = np.asarray(first.visible_centroid_world_m[:2], dtype=np.float64)
    second_xy = np.asarray(second.visible_centroid_world_m[:2], dtype=np.float64)
    point = np.asarray(target.visible_centroid_world_m[:2], dtype=np.float64)
    segment = second_xy - first_xy
    length_sq = float(segment @ segment)
    if length_sq < 0.03**2:
        return {"id": target.id, "fraction_along_references": None,
                "lateral_fraction_of_reference_span": None, "passes": False,
                "reference_geometry_insufficient": True}
    fraction = float((point - first_xy) @ segment / length_sq)
    lateral_fraction = float(np.linalg.norm(point - (first_xy + fraction * segment)) / np.sqrt(length_sq))
    return {
        "id": target.id,
        "fraction_along_references": fraction,
        "lateral_fraction_of_reference_span": lateral_fraction,
        "passes": 0.15 <= fraction <= 0.85 and lateral_fraction <= 0.20,
    }


def bind_visual_pick_place(language: str, scene: VisualSceneSnapshot) -> VisualTaskBinding:
    """Resolve visible IDs; ambiguous or missing evidence returns refusal.

    A successful ID match is not permission to execute: color/other modifiers,
    grasp geometry, support regions and goal verification require later checks.
    """

    if scene.source != "rgbd":
        raise ValueError("visual task binding requires an RGB-D scene")
    try:
        task = parse_visual_pick_place_language(language)
    except ValueError as exc:
        return VisualTaskBinding(scene.snapshot_id, reason="unsupported_language",
                                 evidence={"detail": str(exc)})

    descriptors = tuple(
        phrase for phrase in (task.target_phrase, *task.reference_phrases, task.goal_phrase)
        if len(phrase.split()) > 1
    )
    evidence: dict[str, object] = {}

    def refuse(reason: str) -> VisualTaskBinding:
        return VisualTaskBinding(
            scene.snapshot_id, reason=reason, goal_relation=task.goal_relation,
            unverified_descriptors=descriptors, evidence=evidence,
        )

    goal_candidates = _eligible(scene, category_for_phrase(task.goal_phrase))
    evidence["goal_candidates"] = [item.id for item in goal_candidates]
    shared_references = [
        index for index, phrase in enumerate(task.reference_phrases) if phrase == task.goal_phrase
    ]
    if task.selector == "between" and len(goal_candidates) > 1 and len(shared_references) == 1:
        shared_index = shared_references[0]
        other_index = 1 - shared_index
        other_candidates = _eligible(scene, category_for_phrase(task.reference_phrases[other_index]))
        evidence[f"reference_{other_index}_candidates"] = [item.id for item in other_candidates]
        if len(other_candidates) != 1:
            return refuse("reference_not_observed" if not other_candidates else "reference_ambiguous")
        other = other_candidates[0]
        targets = _eligible(scene, category_for_phrase(task.target_phrase))
        evidence["target_candidates"] = [item.id for item in targets]
        if not targets:
            return refuse("target_not_observed")
        hypotheses = []
        passing = []
        for goal_candidate in goal_candidates:
            if goal_candidate.id == other.id:
                continue
            references = (goal_candidate, other) if shared_index == 0 else (other, goal_candidate)
            for target_candidate in targets:
                if target_candidate.id in {goal_candidate.id, other.id}:
                    continue
                measurement = _between_measurement(target_candidate, *references)
                hypotheses.append({"goal_id": goal_candidate.id, "reference_ids": [
                    item.id for item in references
                ], **measurement})
                if measurement["passes"]:
                    passing.append((goal_candidate, references, target_candidate))
        evidence["between_joint_hypotheses"] = hypotheses
        if len(passing) != 1:
            if hypotheses and all(item.get("reference_geometry_insufficient") for item in hypotheses):
                return refuse("reference_geometry_insufficient")
            return refuse("goal_ambiguous" if len({item[0].id for item in passing}) != 1 else "target_ambiguous")
        goal, references, target = passing[0]
        return VisualTaskBinding(
            snapshot_id=scene.snapshot_id,
            status="candidate_requires_attribute_check" if descriptors else "bound_ids",
            target_id=target.id,
            goal_id=goal.id,
            reference_ids=tuple(item.id for item in references),
            goal_relation=task.goal_relation,
            unverified_descriptors=descriptors,
            evidence=evidence,
        )
    if len(goal_candidates) != 1:
        return refuse("goal_not_observed" if not goal_candidates else "goal_ambiguous")
    goal = goal_candidates[0]

    reference_objects: list[VisualObject] = []
    for phrase in task.reference_phrases:
        candidates = _eligible(scene, category_for_phrase(phrase))
        evidence[f"reference_{len(reference_objects)}_candidates"] = [item.id for item in candidates]
        if len(candidates) != 1:
            return refuse("reference_not_observed" if not candidates else "reference_ambiguous")
        reference_objects.append(candidates[0])
    if len({item.id for item in reference_objects}) != len(reference_objects):
        return refuse("references_not_distinct")

    target_candidates = [
        item for item in _eligible(scene, category_for_phrase(task.target_phrase))
        if item.id != goal.id and item.id not in {ref.id for ref in reference_objects}
    ]
    evidence["target_candidates"] = [item.id for item in target_candidates]
    if not target_candidates:
        return refuse("target_not_observed")

    if task.selector == "between":
        first = np.asarray(reference_objects[0].visible_centroid_world_m[:2], dtype=np.float64)
        second = np.asarray(reference_objects[1].visible_centroid_world_m[:2], dtype=np.float64)
        if float((second - first) @ (second - first)) < 0.03**2:
            return refuse("reference_geometry_insufficient")
        between: list[dict[str, object]] = []
        selected: list[VisualObject] = []
        for item in target_candidates:
            measurement = _between_measurement(item, *reference_objects)
            between.append(measurement)
            if measurement["passes"]:
                selected.append(item)
        evidence["between_xy_visible_centroids"] = between
        if len(selected) != 1:
            return refuse("target_not_between" if not selected else "target_ambiguous")
        target = selected[0]
    elif task.selector == "next_to":
        reference_xy = np.asarray(reference_objects[0].visible_centroid_world_m[:2], dtype=np.float64)
        ranked = sorted(
            (float(np.linalg.norm(np.asarray(item.visible_centroid_world_m[:2]) - reference_xy)), item.id, item)
            for item in target_candidates
        )
        evidence["next_to_xy_visible_centroids"] = [
            {"id": item.id, "distance_m": distance} for distance, _, item in ranked
        ]
        if ranked[0][0] > 0.20:
            return refuse("target_not_next_to")
        if len(ranked) > 1 and ranked[1][0] - ranked[0][0] < 0.04:
            return refuse("target_ambiguous")
        target = ranked[0][2]
    else:
        if len(target_candidates) != 1:
            return refuse("target_ambiguous")
        target = target_candidates[0]

    return VisualTaskBinding(
        snapshot_id=scene.snapshot_id,
        status="candidate_requires_attribute_check" if descriptors else "bound_ids",
        target_id=target.id,
        goal_id=goal.id,
        reference_ids=tuple(item.id for item in reference_objects),
        goal_relation=task.goal_relation,
        unverified_descriptors=descriptors,
        evidence=evidence,
    )

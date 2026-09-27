"""`inside(X, region)` must name a surface that exists, or cuTAMP rejects the goal.

Measured on LIBERO-Goal task04: every `inside(cream_cheese_1_main,
wooden_cabinet_1_top_region)` solve reported `feasible=False, num_satisfying=0` with

    ValueError: Goal atom On(cream_cheese_1_main, wooden_cabinet_1_top_region) references
    unknown surface literal 'wooden_cabinet_1_top_region' ...

raised by cuTAMP's pre-search guard in `cutamp/task_planning/search.py`, while the surface
that exists is `wooden_cabinet_1_top_region_inner_floor` and the same goal expressed with
that name solved with 15 satisfying particles. These tests pin the resolution, and pin that
nothing changes when no surface matches.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional

from experiments.robot.libero.tiptop_repro.cutamp_fluents import (
    map_atom_to_cutamp,
    map_atoms_to_cutamp,
)
from experiments.robot.libero.tiptop_repro.tamp_scene import _container_surface_resolver


class _Surface:
    def __init__(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        self.name = name
        self.geometry = {"kind": "virtual_inner_floor", "metadata": dict(metadata or {})}


REGION = "wooden_cabinet_1_top_region"
FLOOR = "wooden_cabinet_1_top_region_inner_floor"


def _atoms() -> List[Dict[str, Any]]:
    return [{"predicate": "inside", "args": ["cream_cheese_1_main", REGION]}]


class ContainerSurfaceResolutionTests(unittest.TestCase):
    def test_region_resolves_to_the_inner_floor_surface(self):
        resolver = _container_surface_resolver([_Surface(FLOOR), _Surface("table")])
        self.assertEqual(resolver(REGION), FLOOR)

        result = map_atom_to_cutamp(_atoms()[0], container_surface_resolver=resolver)
        self.assertEqual([(f.predicate, f.args) for f in result.fluents], [("on", ("cream_cheese_1_main", FLOOR))])
        self.assertTrue(result.fluents[0].approximated)
        self.assertIn(FLOOR, result.fluents[0].note)
        self.assertTrue(any("resolved inside container" in item for item in result.diagnostics))

    def test_without_a_matching_surface_the_container_is_passed_through(self):
        """No regression: the old behaviour survives when nothing matches."""
        resolver = _container_surface_resolver([_Surface("table")])
        self.assertIsNone(resolver(REGION))

        result = map_atom_to_cutamp(_atoms()[0], container_surface_resolver=resolver)
        self.assertEqual([(f.predicate, f.args) for f in result.fluents], [("on", ("cream_cheese_1_main", REGION))])

    def test_with_no_resolver_at_all_behaviour_is_unchanged(self):
        result = map_atom_to_cutamp(_atoms()[0])
        self.assertEqual([(f.predicate, f.args) for f in result.fluents], [("on", ("cream_cheese_1_main", REGION))])

    def test_a_container_that_is_already_a_surface_name_is_left_alone(self):
        resolver = _container_surface_resolver([_Surface(FLOOR)])
        self.assertEqual(resolver(FLOOR), FLOOR)

    def test_the_region_bookkeeping_on_the_surface_is_also_honoured(self):
        """A surface need not be named after the region it came from."""
        resolver = _container_surface_resolver(
            [_Surface("cabinet_drawer_floor", {"source_bddl_region": REGION})]
        )
        self.assertEqual(resolver(REGION), "cabinet_drawer_floor")

    def test_the_qualified_region_name_also_matches(self):
        resolver = _container_surface_resolver(
            [_Surface("drawer_floor", {"source_bddl_qualified_region": REGION})]
        )
        self.assertEqual(resolver(REGION), "drawer_floor")

    def test_interior_wins_when_several_surfaces_come_from_one_region(self):
        resolver = _container_surface_resolver(
            [
                _Surface(f"{REGION}_rim"),
                _Surface(FLOOR),
                _Surface(f"{REGION}_outer"),
            ]
        )
        self.assertEqual(resolver(REGION), FLOOR)

    def test_candidates_that_merely_share_a_prefix_are_used_only_as_a_fallback(self):
        resolver = _container_surface_resolver([_Surface(f"{REGION}_top_plate")])
        self.assertEqual(resolver(REGION), f"{REGION}_top_plate")

    def test_exact_bookkeeping_beats_a_prefix_match(self):
        resolver = _container_surface_resolver(
            [
                _Surface(f"{REGION}_side"),
                _Surface("floor_panel", {"source_bddl_region": REGION}),
            ]
        )
        self.assertEqual(resolver(REGION), "floor_panel")

    def test_without_approximations_inside_is_still_dropped(self):
        resolver = _container_surface_resolver([_Surface(FLOOR)])
        result = map_atom_to_cutamp(_atoms()[0], allow_approximations=False, container_surface_resolver=resolver)
        self.assertEqual(result.fluents, [])
        self.assertTrue(any("no native cuTAMP fluent" in item for item in result.diagnostics))

    def test_requiresfinal_wrapping_passes_the_resolver_through(self):
        resolver = _container_surface_resolver([_Surface(FLOOR)])
        atom = {"predicate": "requiresfinal", "args": ["inside", "cream_cheese_1_main", REGION]}
        result = map_atom_to_cutamp(atom, container_surface_resolver=resolver)
        self.assertEqual([(f.predicate, f.args) for f in result.fluents], [("on", ("cream_cheese_1_main", FLOOR))])

    def test_map_atoms_passes_the_resolver_through(self):
        resolver = _container_surface_resolver([_Surface(FLOOR)])
        result = map_atoms_to_cutamp(_atoms(), container_surface_resolver=resolver)
        self.assertEqual([(f.predicate, f.args) for f in result.fluents], [("on", ("cream_cheese_1_main", FLOOR))])

    def test_a_direct_on_atom_is_not_touched(self):
        """`on(X, surface)` was already correct and must not be rewritten."""
        resolver = _container_surface_resolver([_Surface(FLOOR)])
        atom = {"predicate": "on", "args": ["cream_cheese_1_main", "plate_1_main"]}
        result = map_atom_to_cutamp(atom, container_surface_resolver=resolver)
        self.assertEqual([(f.predicate, f.args) for f in result.fluents], [("on", ("cream_cheese_1_main", "plate_1_main"))])


if __name__ == "__main__":
    unittest.main()

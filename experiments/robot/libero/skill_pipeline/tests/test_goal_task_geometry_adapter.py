from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[5]
ADAPTER_PATH = (
    REPO_ROOT
    / "skill_packs"
    / "libero_object_task_from_spatial_swap_mining_base_20260918"
    / "code"
    / "geometry_profiles.py"
)


def _load_adapter():
    spec = importlib.util.spec_from_file_location("goal_task_geometry_profiles_test", ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GoalTaskGeometryAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = _load_adapter()
        self.hint = {
            "surface_name": "wine_rack_1_top_region",
            "source_object": "wine_rack_1_main",
            "source_site_name": "wine_rack_1_top_region",
            "site_margin_m": 0.003,
            "min_half_extent_m": 0.024,
            "top_clearance_m": 0.003,
            "thickness_m": 0.006,
        }
        self.task = SimpleNamespace(diagnostics={})

    def test_rack_surface_uses_top_level_geometry_site(self) -> None:
        source = SimpleNamespace(
            name="wine_rack_1_main",
            pos=[0.40, -0.25, 0.01],
            geometry={
                "center": [0.40, -0.25, 0.17],
                "half_extents": [0.13, 0.13, 0.17],
                "sites": [
                    {
                        "name": "wine_rack_1_top_region",
                        "site_id": 27,
                        "pos": [0.4059, -0.1726, 0.2254],
                        "size": [0.10087, 0.022, 0.00251],
                        "quat": [1.0, 0.0, 0.0, 0.0],
                    }
                ],
                "metadata": {},
            },
        )
        scene = SimpleNamespace(objects={"wine_rack_1_main": source})

        descriptor = self.adapter.resolve_surface_descriptor(
            "wine_rack_top_region_surface_v1",
            surface_name="wine_rack_1_top_region",
            scene=scene,
            task=self.task,
            table_geometry={},
            hint=self.hint,
            hint_key="placement_region",
        )

        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertAlmostEqual(descriptor["center"][0], 0.4059, places=6)
        self.assertAlmostEqual(descriptor["center"][1], -0.1726, places=6)
        self.assertAlmostEqual(descriptor["inner_bounds"]["support_z"], 0.23091, places=6)
        self.assertEqual(descriptor["metadata"]["source_site_name"], "wine_rack_1_top_region")

    def test_rack_surface_resolves_only_matching_allowed_contact_objects(self) -> None:
        self.hint["allow_contact_object_matches"] = ["*akita_black_bowl*"]
        source = SimpleNamespace(
            name="wine_rack_1_main",
            pos=[0.40, -0.25, 0.01],
            geometry={
                "sites": [
                    {
                        "name": "wine_rack_1_top_region",
                        "site_id": 27,
                        "pos": [0.4059, -0.1726, 0.2254],
                        "size": [0.10087, 0.022, 0.00251],
                    }
                ]
            },
        )
        scene = SimpleNamespace(
            objects={
                "wine_rack_1_main": source,
                "akita_black_bowl_1_main": SimpleNamespace(name="akita_black_bowl_1_main"),
                "wine_bottle_1_main": SimpleNamespace(name="wine_bottle_1_main"),
            }
        )

        descriptor = self.adapter.resolve_surface_descriptor(
            "wine_rack_top_region_surface_v1",
            surface_name="wine_rack_1_top_region",
            scene=scene,
            task=self.task,
            table_geometry={},
            hint=self.hint,
            hint_key="placement_region",
        )

        self.assertIsNotNone(descriptor)
        assert descriptor is not None
        self.assertEqual(descriptor["metadata"]["allowed_contact_objects"], ["akita_black_bowl_1_main"])

    def test_rack_surface_does_not_fall_back_to_rack_body_origin(self) -> None:
        source = SimpleNamespace(
            name="wine_rack_1_main",
            pos=[0.40, -0.25, 0.01],
            geometry={"metadata": {}},
        )
        scene = SimpleNamespace(objects={"wine_rack_1_main": source})

        descriptor = self.adapter.resolve_surface_descriptor(
            "wine_rack_top_region_surface_v1",
            surface_name="wine_rack_1_top_region",
            scene=scene,
            task=self.task,
            table_geometry={},
            hint=self.hint,
            hint_key="placement_region",
        )

        self.assertIsNone(descriptor)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.generated_benchmark import (
    GenerationConfig,
    SourceTask,
    classify_object,
    classify_target,
    generate_candidates,
    split_candidates,
    write_generated_benchmark,
)


BDDL_BOWL_ON_PLATE = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language pick up the black bowl next to the plate and place it on the plate)
  (:fixtures
    kitchen_table - kitchen_table
    flat_stove_1 - flat_stove
    wooden_cabinet_1 - wooden_cabinet
  )
  (:objects
    akita_black_bowl_1 - akita_black_bowl
    akita_black_bowl_2 - akita_black_bowl
    plate_1 - plate
  )
  (:obj_of_interest
    akita_black_bowl_1
    plate_1
  )
  (:goal
    (And (On akita_black_bowl_1 plate_1))
  )
)
"""

BDDL_CREAM_CHEESE_IN_BASKET = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language pick up the cream cheese box and put it in the basket)
  (:fixtures
    kitchen_table - kitchen_table
  )
  (:objects
    cream_cheese_1 - cream_cheese
    butter_1 - butter
    basket_1 - basket
    akita_black_bowl_1 - akita_black_bowl
  )
  (:obj_of_interest
    cream_cheese_1
    basket_1
  )
  (:goal
    (And (In cream_cheese_1 basket_1_contain_region))
  )
)
"""

BDDL_BOOK_CADDY = """
(define (problem LIBERO_Study_Tabletop_Manipulation)
  (:language pick up the book and place it in the front compartment of the caddy)
  (:regions
    (front_contain_region
      (:target desk_caddy_1)
    )
  )
  (:fixtures
    study_table - study_table
    desk_caddy_1 - desk_caddy
  )
  (:objects
    black_book_1 - black_book
    white_yellow_mug_1 - white_yellow_mug
  )
  (:obj_of_interest
    black_book_1
    desk_caddy_1
  )
  (:goal
    (And (In black_book_1 desk_caddy_1_front_contain_region))
  )
)
"""


class GeneratedBenchmarkTests(unittest.TestCase):
    def test_inventory_classifies_scene_parts(self):
        source = SourceTask.from_bddl(suite="libero_90", task_id_1based=38, bddl_text=BDDL_BOWL_ON_PLATE)
        self.assertEqual(source.language, "pick up the black bowl next to the plate and place it on the plate")
        self.assertIn("akita_black_bowl_1", source.objects)
        self.assertIn("flat_stove_1", source.fixtures)
        self.assertEqual(source.goal_atoms[0].predicate, "on")
        self.assertEqual(classify_object("white_yellow_mug_1"), "mug")
        self.assertEqual(classify_target("wooden_cabinet_1_cabinet_top"), "surface")
        self.assertEqual(classify_target("basket_1_contain_region"), "container")

    def test_generates_controlled_variants(self):
        sources = [
            SourceTask.from_bddl(suite="libero_90", task_id_1based=1, bddl_text=BDDL_BOWL_ON_PLATE),
            SourceTask.from_bddl(suite="libero_90", task_id_1based=2, bddl_text=BDDL_CREAM_CHEESE_IN_BASKET),
            SourceTask.from_bddl(suite="libero_90", task_id_1based=3, bddl_text=BDDL_BOOK_CADDY),
        ]
        cfg = GenerationConfig(max_candidates_per_source=20, validation_limit=10, train_limit=30)
        candidates = generate_candidates(sources, cfg)
        self.assertGreaterEqual(len(candidates), 6)
        templates = {task.template for task in candidates}
        self.assertIn("pick_place_on_surface", templates)
        self.assertIn("put_inside_container", templates)
        self.assertIn("caddy_compartment", templates)
        ambiguous_inside = [
            task
            for task in candidates
            if task.template == "put_inside_container" and "black bowl and place it in the akita black bowl" in task.language
        ]
        self.assertEqual(ambiguous_inside, [])

        caddy = next(task for task in candidates if task.template == "caddy_compartment" and "left compartment" in task.language)
        self.assertIn("(define (problem LIBERO_Study_Tabletop_Manipulation)", caddy.bddl_text)
        self.assertNotIn(f"(define (problem {caddy.task_id})", caddy.bddl_text)
        self.assertIn("(in", caddy.bddl_text)
        self.assertIn("desk_caddy_1_left_contain_region", caddy.bddl_text)
        self.assertIn("(left_contain_region", caddy.bddl_text)
        self.assertIn("geometry", caddy.tags)

    def test_splits_and_writes_benchmark_directory(self):
        sources = [
            SourceTask.from_bddl(suite="libero_90", task_id_1based=1, bddl_text=BDDL_BOWL_ON_PLATE),
            SourceTask.from_bddl(suite="libero_90", task_id_1based=2, bddl_text=BDDL_CREAM_CHEESE_IN_BASKET),
            SourceTask.from_bddl(suite="libero_90", task_id_1based=3, bddl_text=BDDL_BOOK_CADDY),
        ]
        cfg = GenerationConfig(
            max_candidates_per_source=20,
            train_limit=20,
            validation_limit=10,
            smoke_per_template=1,
            canonical_episodes_per_task=3,
        )
        candidates = generate_candidates(sources, cfg)
        splits = split_candidates(candidates, cfg)
        self.assertTrue(splits["smoke"])
        self.assertTrue(splits["validation"])
        self.assertTrue(splits["train"])

        with tempfile.TemporaryDirectory() as td:
            summary = write_generated_benchmark(td, sources=sources, splits=splits, config=cfg)
            root = Path(td)
            self.assertEqual(summary["source_tasks"], 3)
            self.assertTrue((root / "inventory/libero_90_tasks.jsonl").exists())
            self.assertTrue((root / "manifests/all_tasks.jsonl").exists())
            self.assertTrue((root / "seeds/canonical_episodes.json").exists())
            self.assertTrue(list((root / "task_specs/smoke").glob("*.bddl")))
            canonical = json.loads((root / "seeds/canonical_episodes.json").read_text(encoding="utf-8"))
            self.assertEqual(canonical["episodes_per_task"], 3)


if __name__ == "__main__":
    unittest.main()

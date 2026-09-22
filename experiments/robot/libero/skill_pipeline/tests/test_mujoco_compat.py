from __future__ import annotations

import unittest
from types import SimpleNamespace

from experiments.robot.libero.tiptop_repro.mujoco_compat import model_name_to_id, model_names


class ShortenedNameTableModel:
    """robosuite-shaped model whose ``geom_names`` tuple lists only the NAMED geoms.

    Reproduces the libero_90 KITCHEN_SCENE case (182 geoms, 4 unnamed, tuple of 178)
    in miniature: 6 geoms with ids 0..5, unnamed at ids 1 and 4.  ``geom_id2name`` is
    id-addressed and therefore correct.
    """

    ngeom = 6
    geom_names = ("a", "b", "c", "d")
    _truth = ("a", "", "b", "c", "", "d")

    def geom_id2name(self, index):
        return self._truth[index]

    def geom_name2id(self, name):
        # robosuite builds this from the same shortened tuple, so it is shifted too.
        return list(self.geom_names).index(name)


class AlignedNameTableModel:
    """A model whose ``*_names`` tuple is complete; it must keep being trusted."""

    ngeom = 3
    geom_names = ("x", "", "z")

    def geom_id2name(self, index):  # pragma: no cover - must never be consulted
        raise AssertionError("an index-aligned name table must be used as-is")


class NoCountModel:
    """A model that exposes the legacy table but no count attribute."""

    geom_names = ("only",)


class MujocoCompatNamesTest(unittest.TestCase):
    def test_shortened_table_is_rebuilt_per_id(self):
        names = model_names(ShortenedNameTableModel(), "geom")
        self.assertEqual(names, ["a", "", "b", "c", "", "d"])
        self.assertEqual(len(names), ShortenedNameTableModel.ngeom)

    def test_shortened_table_would_shift_ids(self):
        # The regression this guards: indexing the raw tuple puts 'b' on id 1, which is
        # the UNNAMED geom, and every later name onto the wrong id as well.
        raw = list(ShortenedNameTableModel.geom_names)
        self.assertNotEqual(raw[1], "")
        self.assertNotEqual(raw[3], "c")

    def test_aligned_table_is_returned_verbatim(self):
        self.assertEqual(model_names(AlignedNameTableModel(), "geom"), ["x", "", "z"])

    def test_table_without_count_is_returned(self):
        self.assertEqual(model_names(NoCountModel(), "geom"), ["only"])

    def test_unknown_kind_and_missing_model(self):
        self.assertEqual(model_names(ShortenedNameTableModel(), "camera"), [])
        self.assertEqual(model_names(None, "geom"), [])

    def test_name_to_id_uses_id_addressed_names(self):
        model = ShortenedNameTableModel()
        self.assertEqual(model_name_to_id(model, "geom", "a"), 0)
        self.assertEqual(model_name_to_id(model, "geom", "b"), 2)
        self.assertEqual(model_name_to_id(model, "geom", "c"), 3)
        self.assertEqual(model_name_to_id(model, "geom", "d"), 5)
        # 'b' sits at compacted index 1, which is named '' on the raw table.
        self.assertNotEqual(model_name_to_id(model, "geom", "b"), 1)

    def test_name_to_id_rejects_a_shifted_name2id_answer(self):
        self.assertIsNone(model_name_to_id(ShortenedNameTableModel(), "geom", "missing"))

    def test_name_to_id_keeps_aligned_answers(self):
        self.assertEqual(model_name_to_id(AlignedNameTableModel(), "geom", "z"), 2)


class DataFieldTest(unittest.TestCase):
    def test_legacy_then_modern_spelling(self):
        from experiments.robot.libero.tiptop_repro.mujoco_compat import data_field

        self.assertEqual(data_field(SimpleNamespace(xpos="legacy"), "xpos", "geom_xpos"), "legacy")
        self.assertEqual(data_field(SimpleNamespace(geom_xpos="modern"), "xpos", "geom_xpos"), "modern")
        self.assertIsNone(data_field(None, "xpos", "geom_xpos"))
        self.assertIsNone(data_field(SimpleNamespace(), "xpos", "geom_xpos"))


if __name__ == "__main__":
    unittest.main()

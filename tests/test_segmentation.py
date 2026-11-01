import unittest
from unittest.mock import patch

import numpy as np

from tpbocr import segment


def word(text, x, y, width, line):
    return {"text": text, "x": x, "y": y, "w": width, "h": 20,
            "conf": 96, "line": (1, 1, line)}


class SegmentationTests(unittest.TestCase):
    def tokens(self, words):
        with patch.object(segment, "_words", return_value=words):
            return segment.tokens(np.full((1000, 1000), 255, dtype=np.uint8))

    def test_standalone_final_remedies_stay_with_their_rubrics(self):
        tokens = self.tokens([
            word("Anxiety.—Verat.,", 210, 250, 250, 1),
            word("Zinc.", 210, 300, 50, 2),
            word("Excitement.—Ars.,", 210, 350, 260, 3),
            word("Zine.", 210, 400, 50, 4),
            word("Fretfulness.—Fer.,", 210, 450, 260, 5),
        ])
        remedies = [(t["rubric"], t["text"]) for t in tokens if not t["is_heading"]]
        self.assertIn(("Anxiety", "Zinc."), remedies)
        self.assertIn(("Excitement", "Zine."), remedies)
        self.assertEqual(len(remedies), 5)

    def test_centered_section_heading_is_still_removed(self):
        tokens = self.tokens([
            word("Anxiety.—Acon.,", 210, 250, 250, 1),
            word("Intellect.", 430, 300, 140, 2),
            word("Disposition.—Ars.,", 210, 350, 260, 3),
        ])
        self.assertEqual([(t["rubric"], t["text"]) for t in tokens if not t["is_heading"]],
                         [("Anxiety", "Acon.,"), ("Disposition", "Ars.,")])

    def test_running_heads_still_do_not_merge_with_a_remedy(self):
        tokens = self.tokens([
            word("19", 210, 100, 30, 1),
            word("MIND.", 440, 100, 120, 1),
            word("Acon.,", 210, 250, 90, 2),
        ])
        self.assertEqual([t["text"] for t in tokens], ["Acon.,"])

    def test_heading_cleans_separator_noise_without_changing_raw_text(self):
        tokens = self.tokens([
            word("Anxiety.—Acon.,", 210, 250, 250, 1),
            word("-", 210, 300, 15, 2),
            word("Avarice.—ARS.,", 240, 300, 250, 2),
        ])
        heading = next(t for t in tokens if t["is_heading"] and "Avarice" in t["text"])
        self.assertEqual(heading["rubric"], "Avarice")
        self.assertEqual(heading["text"], "- Avarice.")
        self.assertEqual(tokens[-1]["rubric"], "Avarice")

    def test_multiword_heading_keeps_internal_hyphen(self):
        tokens = self.tokens([
            word("Anxiety.—Acon.,", 210, 250, 250, 1),
            word("Disposition", 210, 300, 120, 2),
            word("-", 340, 300, 15, 2),
            word("generally", 365, 300, 100, 2),
            word("affected.—Ars.,", 475, 300, 220, 2),
        ])
        self.assertEqual(tokens[-1]["rubric"], "Disposition - generally affected")


if __name__ == "__main__":
    unittest.main()

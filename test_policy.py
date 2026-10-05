"""Policy calibration cases (signals from the 2026-10-05 example images). Run: python -m unittest"""
import unittest
from policy import evaluate

CATS = ["sexual", "violence", "violence/graphic", "self-harm", "self-harm/intent", "self-harm/instructions"]


def case(sexual, hentai, porn, nudenet=(), **flags):
    categories = {c: False for c in CATS} | {"sexual": sexual} | {k.replace("_", "/"): v for k, v in flags.items()}
    return ({"categories": categories},
            {"drawings": 0.1, "hentai": hentai, "neutral": 0.5, "porn": porn, "sexy": 0.0},
            [{"class": c, "score": s} for c, s in nudenet])


class PolicyTests(unittest.TestCase):
    def check(self, expected, *args, **kw):
        self.assertEqual(expected, evaluate(*case(*args, **kw))[0])

    def test_mystique_body_paint_reviews(self): self.check("review", True, 0.10, 0.22, [("MALE_BREAST_EXPOSED", 0.64)])
    def test_suggestive_anime_card_reviews(self): self.check("review", True, 0.19, 0.0)
    def test_explicit_photo_rejects(self): self.check("reject", True, 0.0, 1.0, [("FEMALE_BREAST_EXPOSED", 0.85)])
    def test_explicit_drawing_rejects(self): self.check("reject", True, 0.80, 0.0, [("FEMALE_BREAST_EXPOSED", 0.67)])
    def test_ordinary_card_allows(self): self.check("allow", False, 0.03, 0.02)
    def test_gantman_alone_never_escalates(self): self.check("allow", False, 0.80, 0.05)
    def test_nudity_openai_missed_reviews(self): self.check("review", False, 0.1, 0.1, [("FEMALE_GENITALIA_EXPOSED", 0.70)])
    def test_graphic_violence_rejects(self): self.check("reject", False, 0, 0, violence_graphic=True)

    def test_duplicate_detections_reported_once_at_max(self):
        _, reasons = evaluate(*case(True, 0, 0, [("FEMALE_BREAST_EXPOSED", 0.66), ("FEMALE_BREAST_EXPOSED", 0.70)]))
        self.assertEqual(["openai:sexual", "nudenet:FEMALE_BREAST_EXPOSED 0.70"], reasons)


if __name__ == "__main__":
    unittest.main()

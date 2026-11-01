# -*- coding: utf-8 -*-
"""Shape model: per-(letter, face) glyph prototypes + token classifier.

A face is 2=Roman, 3=Italic, 4=Antique. For each lower-case letter we average
the size-normalised bitmaps of every training glyph of that (letter, face) into
a prototype. To classify a token we match each of its letters to the three
prototypes of that same letter and accumulate the evidence; the face with the
best total similarity wins. Aggregating 4-6 letters' *shapes* resolves the
Roman/Antique overlap that a single stroke-weight scalar cannot.
"""
import pickle
import numpy as np

FACES = (2, 3, 4)


class ShapeModel:
    def __init__(self):
        self.proto = {}          # (letter, face) -> mean bitmap (float32)
        self.count = {}          # (letter, face) -> n

    # ---- training -------------------------------------------------------
    def fit(self, samples):
        """samples: list of (letter, face, glyph_bitmap)."""
        acc = {}
        for letter, face, g in samples:
            k = (letter, face)
            if k not in acc:
                acc[k] = [np.zeros_like(g), 0]
            acc[k][0] += g
            acc[k][1] += 1
        for k, (s, n) in acc.items():
            self.proto[k] = s / n
            self.count[k] = n
        return self

    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump({"proto": self.proto, "count": self.count}, f)

    @classmethod
    def load(cls, path):
        m = cls()
        d = pickle.load(open(path, "rb"))
        m.proto, m.count = d["proto"], d["count"]
        return m

    # ---- scoring --------------------------------------------------------
    @staticmethod
    def _sim(a, b):
        """Zero-mean normalised cross-correlation of two bitmaps in [-1,1]."""
        a = a - a.mean(); b = b - b.mean()
        d = (np.linalg.norm(a) * np.linalg.norm(b))
        if d < 1e-6:
            return 0.0
        return float((a * b).sum() / d)

    def classify(self, glyphs, min_letters=1):
        """glyphs: list of (letter, bitmap). Returns dict(face, confidence,
        votes, scores) or None if no usable letter."""
        totals = {f: 0.0 for f in FACES}
        used = 0
        votes = {f: 0 for f in FACES}
        for letter, g in glyphs:
            avail = [f for f in FACES if (letter, f) in self.proto
                     and self.count[(letter, f)] >= 2]
            if len(avail) < 2:
                continue
            sims = {f: self._sim(g, self.proto[(letter, f)]) for f in avail}
            used += 1
            best = max(sims, key=sims.get)
            votes[best] += 1
            for f, s in sims.items():
                totals[f] += s
        if used < min_letters:
            return None
        face = max(totals, key=lambda f: totals[f])
        ordered = sorted(totals.values(), reverse=True)
        margin = (ordered[0] - ordered[1]) / (used or 1)
        conf = round(min(1.0, max(0.0, 0.5 + margin)), 3)
        return dict(face=face, confidence=conf, used=used,
                    votes=votes, scores={f: round(totals[f] / used, 3)
                                         for f in totals})

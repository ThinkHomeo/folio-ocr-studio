# -*- coding: utf-8 -*-
"""Trained glyph face-classifier (scikit-learn MLP), packaged for the pipeline.

Learns Roman(2)/Italic(3)/Antique(4) from the vision-gold glyph bitmaps plus a
per-page-normalised weight & slant. Classifies each lower-case glyph of a token
and averages the class-probabilities. This is the upgraded primary engine;
CAPS(5)/parens(1) are still read from the token text.
"""
import pickle
import numpy as np
import cv2

G = 20   # glyph downsample side


def glyph_vec(g):
    gg = cv2.resize(g.astype(np.float32), (G, G), interpolation=cv2.INTER_AREA)
    return gg.flatten()


def token_vecs(glyphs, feat, norm):
    """per-glyph feature rows for one token (or [] if no glyphs/feat)."""
    if not glyphs or not feat:
        return []
    m, mad = norm
    zw = (feat["weight"] - m) / mad
    extra = [zw, feat["slant"] / 20.0, abs(feat["slant"]) / 20.0]
    return [np.concatenate([glyph_vec(g), extra]) for _, g in glyphs]


def page_norm(weights_upright):
    w = np.asarray(weights_upright, float)
    if len(w) == 0:
        return (0.26, 0.03)
    m = np.median(w); mad = np.median(np.abs(w - m)) * 1.4826 + 1e-6
    return (float(m), float(mad))


class MLPFace:
    def __init__(self, clf=None):
        self.clf = clf

    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump(self.clf, f)

    @classmethod
    def load(cls, path):
        return cls(pickle.load(open(path, "rb")))

    def classify(self, glyphs, feat, norm):
        """-> dict(face, confidence) or None if no glyphs."""
        V = token_vecs(glyphs, feat, norm)
        if not V:
            return None
        proba = self.clf.predict_proba(np.array(V)).mean(0)
        cls = self.clf.classes_
        i = int(np.argmax(proba))
        order = np.sort(proba)[::-1]
        margin = float(order[0] - order[1]) if len(order) > 1 else 1.0
        return dict(face=int(cls[i]), confidence=round(float(proba[i]), 3),
                    margin=round(margin, 3))


def train(samples):
    """samples: list of (feature_row, face). Returns a fitted MLPFace."""
    from sklearn.neural_network import MLPClassifier
    X = np.array([s[0] for s in samples]); y = np.array([s[1] for s in samples])
    clf = MLPClassifier(hidden_layer_sizes=(120,), max_iter=600,
                        alpha=1e-3, random_state=0).fit(X, y)
    return MLPFace(clf)

# -*- coding: utf-8 -*-
"""Multi-feature, per-page-normalised face classifier (2/3/4).

Insight from the gold data: within ANY page Antique sits above Roman on THREE
correlated signals (run-length weight, dt stroke, ink density) while Italic is
set apart by slant; but absolute values drift between pages (heavier inking on
p19 shifts everything up). So we z-normalise each page against its own token
bulk (which is mostly Roman) and let a 3-class Gaussian LDA combine the signals
— far better separation than a single weight threshold.
"""
import numpy as np

FACES = (2, 3, 4)
SLANT_UP = 6.5


def _page_stats(rows):
    """median/MAD of weight,density,stroke_w over this page's upright tokens."""
    W, D, S = [], [], []
    for r in rows:
        f = r["feat"]
        if not f:
            continue
        if abs(f["slant"]) < SLANT_UP:
            W.append(f["weight"]); D.append(f["density"]); S.append(f.get("stroke_w", 0))
    def ms(x):
        x = np.asarray(x, float)
        m = np.median(x); mad = np.median(np.abs(x - m)) + 1e-6
        return m, 1.4826 * mad
    return dict(w=ms(W), d=ms(D), s=ms(S))


def featvec(f, st):
    zw = (f["weight"] - st["w"][0]) / st["w"][1]
    zd = (f["density"] - st["d"][0]) / st["d"][1]
    zs = (f.get("stroke_w", 0) - st["s"][0]) / st["s"][1]
    return np.array([zw, zd, zs, f["slant"], abs(f["slant"])], float)


class LDA:
    """Gaussian LDA with shared (regularised) covariance."""
    def fit(self, X, y):
        self.cls = sorted(set(y))
        self.mu = {}; self.prior = {}
        d = X.shape[1]; Sw = np.zeros((d, d))
        for c in self.cls:
            Xc = X[y == c]
            self.mu[c] = Xc.mean(0); self.prior[c] = len(Xc) / len(X)
            Sw += (Xc - self.mu[c]).T @ (Xc - self.mu[c])
        Sw = Sw / len(X) + 1e-3 * np.eye(d)
        self.P = np.linalg.inv(Sw)
        return self

    def predict(self, X):
        out = []
        for x in X:
            best, bc = -1e18, None
            for c in self.cls:
                diff = x - self.mu[c]
                score = -0.5 * diff @ self.P @ diff + np.log(self.prior[c] + 1e-9)
                if score > best:
                    best, bc = score, c
            out.append(bc)
        return np.array(out)

    def predict_conf(self, x):
        sc = {}
        for c in self.cls:
            diff = x - self.mu[c]
            sc[c] = -0.5 * diff @ self.P @ diff + np.log(self.prior[c] + 1e-9)
        order = sorted(sc.values(), reverse=True)
        best = max(sc, key=sc.get)
        margin = order[0] - order[1] if len(order) > 1 else 5.0
        conf = float(1 / (1 + np.exp(-margin)))
        return best, round(conf, 3)

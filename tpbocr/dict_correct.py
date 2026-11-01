# -*- coding: utf-8 -*-
"""Dictionary auto-correct for OCR'd remedy abbreviations — text to ~100%
without vision. The TPB uses a FIXED vocabulary of remedy abbreviations; we
build that vocabulary from the vision-gold pages (the book's own orthography,
public-domain) and snap each machine OCR token to its nearest known spelling
(e.g. 'Mere.'->'Merc.', 'Dule.'->'Dulc.', 'Cale. ph.'->'Calc. ph.').
"""
import re, glob, os, json, collections


def norm(s):
    """comparison key: lower-case, letters/space only, collapsed."""
    s = s.lower()
    s = re.sub(r"[^a-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_rank_md(t):
    return re.sub(r"[*()]|\*\*", "", t).strip()


def build_vocab(gold_md_paths):
    """-> dict(norm_key -> canonical_surface) from gold .md remedy tokens."""
    surf_counts = collections.defaultdict(collections.Counter)
    for p in gold_md_paths:
        for line in open(p, encoding="utf-8"):
            m = re.match(r"\*\*(.+?)\.\*\*\s*[—-]+\s*(.*)", line.strip())
            if not m:
                continue
            for tok in m.group(2).split(","):
                s = _strip_rank_md(tok)
                if not s:
                    continue
                k = norm(s)
                if k:
                    surf_counts[k][s.rstrip(".,")] += 1
    vocab = {}
    for k, c in surf_counts.items():
        vocab[k] = c.most_common(1)[0][0]
    return vocab


def _lev(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > 3:
        return abs(la - lb)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i-1] == b[j-1] else 1
            cur[j] = min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + cost)
        prev = cur
    return prev[lb]


def correct(text, vocab, vkeys=None):
    """Snap OCR text to the nearest known remedy spelling — CONSERVATIVELY,
    because a wrong snap changes the remedy's identity (Cannab. vs Cinnab. are
    different drugs). Returns (corrected_text, matched_key, distance, uncertain).
    uncertain=True means leave the raw text and send it to review."""
    k = norm(text)
    if not k:
        return text, None, 99, True
    if k in vocab:
        return vocab[k], k, 0, False
    # garbled tokens (OCR noise chars / digits) are unsafe to snap — a lost
    # letter can make a fragment match a DIFFERENT drug (Cannab.->Cinnab.,
    # Nat. c.->Naj). Flag them for review instead of guessing.
    if re.search(r"[^A-Za-z.,'\- ]", text.strip()):
        return text, None, 99, True
    if len(k.replace(" ", "")) < 3:          # fragments too short to be safe
        return text, None, 99, True
    nwords = len(k.split())
    cand = [vk for vk in (vkeys or vocab.keys())
            if len(vk.split()) == nwords and vk[:1] == k[:1]]  # first letter must match
    if not cand:
        return text, None, 99, True
    scored = sorted((_lev(k, vk), vk) for vk in cand)
    best_d, best_k = scored[0]
    second_d = scored[1][0] if len(scored) > 1 else 99
    # a 3-letter single word fixed by 1 edit is too risky (fragment/first-letter
    # OCR confusion can hit a DIFFERENT drug: Ant->Act, Nat->Naj, Iod->Led) -> review
    if nwords == 1 and len(k) < 4:
        return text, None, best_d, True
    if best_d <= 1 and best_d < second_d:
        return vocab[best_k], best_k, best_d, False
    return text, None, best_d, True


# convenience: default vocab from this book's gold pages
def default_vocab(ocr_out_dir):
    paths = sorted(glob.glob(os.path.join(ocr_out_dir, "*_bp0*.md")))
    return build_vocab(paths)

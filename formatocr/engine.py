"""Lossless ingestion and a conservative adapter around the research engine."""
import hashlib
import importlib.metadata
import math
import re
import shutil
from pathlib import Path

from PIL import Image, ImageOps, ImageSequence
from tpbocr import dict_correct
from .dependencies import resolve_tesseract

REPO = Path(__file__).resolve().parents[1]
ALLOWED = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".jp2", ".pdf"}
MAX_PAGES = 500
OVERLAY_PALETTE = ((198, 40, 40), (216, 120, 0), (26, 122, 60),
                   (30, 90, 200), (120, 60, 170))


def checksum(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def generated_overlay_reason(path=None, original_name=None):
    """Identify proof/overlay images that must never be fed back into OCR.

    The research pipeline draws rank-coloured rectangles directly into
    ``*_overlay.png`` files. OCR interprets those borders as ``[`` and ``]``
    characters, so comma-delimited remedies collapse into page-wide tokens.
    Check both the filename and the distinctive five-colour overlay palette.
    """
    name = Path(original_name or path or "").stem.lower()
    if re.search(r"(?:^|[_. -])overlay(?:$|[_. -])", name):
        return ("This is a generated OCR overlay/proof image. Upload the original "
                "scan instead (for example p029.webp, not p029_overlay.png).")
    if not path or not Path(path).is_file() or Path(path).suffix.lower() == ".pdf":
        return None
    try:
        import numpy as np
        with Image.open(path) as image:
            image.seek(0)
            sample = image.convert("RGB")
            sample.thumbnail((1800, 1800), Image.Resampling.NEAREST)
            pixels = np.asarray(sample, dtype=np.int16)
        hits = []
        for color in OVERLAY_PALETTE:
            delta = np.abs(pixels - np.asarray(color, dtype=np.int16))
            # Small tolerance also catches JPEG-compressed copies of an overlay.
            hits.append(int(np.count_nonzero(np.max(delta, axis=2) <= 12)))
        if sum(count >= 12 for count in hits) >= 3 and sum(hits) >= 100:
            return ("This image contains the generated TPB rank-box overlay. "
                    "Upload the clean source scan; annotated overlay images cannot be OCRed reliably.")
    except (OSError, ValueError):
        # Normal upload validation will report unreadable files during ingest.
        return None
    return None


def guarded_correct(raw, vocab):
    # Validate before normalization; punctuation must not hide missing letters.
    clean = re.sub(r"[,;]+$", "", raw.strip()).strip()
    if clean.startswith("(") and clean.endswith(")"):
        clean = clean[1:-1].strip()
    if not re.fullmatch(r"[A-Za-z .'-]+", clean):
        return clean, True, "non-letter-noise"
    cor, key, distance, uncertain = dict_correct.correct(clean, vocab)
    if not uncertain and distance:
        old_words, new_words = dict_correct.norm(clean).split(), dict_correct.norm(cor).split()
        if len(old_words) > 1 and old_words[1:] != new_words[1:]:
            return clean, True, "suffix-identity-change"
    return (clean if uncertain else cor), uncertain, ("unknown-or-ambiguous" if uncertain else f"lexicon-distance-{distance}")


def build_vocab():
    # This deliberately incomplete starter list uses printed examples, never
    # grades from the legacy derived reference datasets (some reverse 1 and 5).
    path = Path(__file__).parent / "lexicon_tpb1891.json"
    if path.exists():
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("remedies", [])
        if isinstance(entries, list):
            vocab = {}
            for entry in entries:
                if isinstance(entry, dict):
                    text = entry.get("abbrev") or entry.get("abbreviation") or entry.get("abbr")
                    if isinstance(text, str):
                        vocab[dict_correct.norm(text)] = text
            if vocab:
                return vocab, {"path": str(path), "sha256": checksum(path), "entries": len(vocab),
                               "scope": data.get("scope"), "provenance": data.get("provenance")}
    # A missing printed dictionary never licenses fuzzy guessing. Exact authority
    # lookup can still assist review, but ambiguous/unmatched identities abstain.
    return {}, {"path": None, "entries": 0, "note": "No printed abbreviation lexicon loaded; identity requires review."}


def ingest(path, output, first_index=0):
    """Yield lossless PNG pages; retain the original uploaded file separately."""
    def save(im, index):
        im = ImageOps.exif_transpose(im).convert("L")
        if im.width * im.height > 90_000_000:
            raise ValueError("Page exceeds the 90 megapixel processing limit.")
        target = output / f"page-{index + 1:04d}.png"
        im.save(target)
        return target

    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(str(path)) as pdf:
            if len(pdf) + first_index > MAX_PAGES:
                raise ValueError("A job supports at most 500 pages.")
            for index in range(len(pdf)):
                page = pdf[index]
                try:
                    if page.get_width() * page.get_height() * (300 / 72) ** 2 > 90_000_000:
                        raise ValueError("PDF page exceeds the processing limit.")
                    bitmap = page.render(scale=300 / 72)
                    try:
                        yield save(bitmap.to_pil(), first_index + index)
                    finally:
                        bitmap.close()
                finally:
                    page.close()
    else:
        with Image.open(path) as image:
            for index, frame in enumerate(ImageSequence.Iterator(image)):
                if first_index + index >= MAX_PAGES:
                    raise ValueError("A job supports at most 500 pages.")
                yield save(frame.copy(), first_index + index)


def triage(rem, threshold, identity_uncertain, chapter, rubric):
    reasons = []
    votes = [rem.get(k) for k in ("scalar_rank", "mlp_rank", "shape_rank")]
    rank = rem["rank"]
    confidence = rem.get("confidence") or 0
    if identity_uncertain:
        reasons.append("remedy-identity")
    if not rubric:
        reasons.append("rubric-continuation")
    if rem.get("flag"):
        reasons.append("engine-review-flag")
    if rank in (2, 3, 4):
        if any(v is None for v in votes):
            reasons.append("missing-classifier-vote")
        elif len(set(votes)) != 1:
            reasons.append("classifier-disagreement")
        if confidence < 0.8:
            reasons.append("low-machine-confidence")
        feat = rem.get("features") or {}
        if not feat:
            reasons.append("missing-features")
        elif feat.get("xheight", 0) < 12:
            reasons.append("low-source-resolution")
        if rank in (2, 4) and (not threshold or abs(feat.get("weight", 0) - threshold) / threshold < 0.10):
            reasons.append("weight-boundary")
    raw = re.sub(r"[,;]+$", "", rem.get("raw", rem["text"]).strip())
    if rank == 1 and not (raw.startswith("(") and raw.endswith(")")):
        reasons.append("unbalanced-parentheses")
    ocr = rem.get("ocr_confidence")
    if ocr is None or not math.isfinite(ocr) or ocr < 0.8:
        reasons.append("low-or-missing-ocr-confidence")
    return list(dict.fromkeys(reasons))


class Engine:
    def __init__(self, tess=None, model_dir=None):
        self.tess = resolve_tesseract(tess)
        model_dir = Path(model_dir) if model_dir else REPO / "out"
        self.mlp = model_dir / "mlp_model.pkl"
        self.shape = model_dir / "shape_model.pkl"
        self.vocab, self.lexicon = build_vocab()

    def diagnostics(self):
        return {"tesseract": self.tess, "tesseract_available": Path(self.tess).is_file(),
                "models": {"mlp": str(self.mlp) if self.mlp.exists() else None,
                           "shape": str(self.shape) if self.shape.exists() else None},
                "lexicon": self.lexicon,
                "profile": "TPB 1891; other editions require separate validation"}

    def manifest(self):
        packages = {}
        for name in ("numpy", "Pillow", "opencv-python-headless", "pytesseract", "scikit-learn"):
            try:
                packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                packages[name] = None
        return {**self.diagnostics(), "packages": packages,
                "model_hashes": {name: checksum(path) if path.exists() else None
                                 for name, path in (("mlp", self.mlp), ("shape", self.shape))},
                "engine_source_sha256": checksum(REPO / "tpbocr" / "pipeline.py"),
                "parameters": {"scale": 1, "pdf_dpi": 300, "confidence_min": 0.8, "weight_margin": 0.1}}

    def process(self, path):
        from tpbocr import pipeline
        doc, _ = pipeline.process(str(path), tess=self.tess,
                                  mlp_model_path=str(self.mlp) if self.mlp.exists() else None,
                                  shape_model_path=str(self.shape) if self.shape.exists() else None)
        return doc

    def process_plain(self, path, language="eng", layout="auto"):
        """Run ordinary page OCR without TPB remedy or typography classification."""
        import pytesseract
        from pytesseract import Output

        pytesseract.pytesseract.tesseract_cmd = self.tess
        psm = {"auto": 3, "single-column": 4, "uniform-block": 6}.get(layout, 3)
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            data = pytesseract.image_to_data(
                image, lang=language, config=f"--oem 1 --psm {psm}", output_type=Output.DICT
            )
            image_size = list(image.size)

        groups = {}
        order = []
        confidences = []
        for index, raw_word in enumerate(data.get("text", [])):
            word = (raw_word or "").strip()
            if not word:
                continue
            key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
            if key not in groups:
                groups[key] = {"words": [], "boxes": [], "confidences": []}
                order.append(key)
            left, top = int(data["left"][index]), int(data["top"][index])
            width, height = int(data["width"][index]), int(data["height"][index])
            try:
                confidence = float(data["conf"][index])
            except (TypeError, ValueError):
                confidence = -1
            groups[key]["words"].append(word)
            groups[key]["boxes"].append((left, top, left + width, top + height))
            if confidence >= 0:
                normalized = confidence / 100
                groups[key]["confidences"].append(normalized)
                confidences.append(normalized)

        lines = []
        text_lines = []
        previous_paragraph = None
        for key in order:
            group = groups[key]
            paragraph = key[:2]
            if previous_paragraph is not None and paragraph != previous_paragraph:
                text_lines.append("")
            previous_paragraph = paragraph
            boxes = group["boxes"]
            line_text = " ".join(group["words"])
            line_confidence = (sum(group["confidences"]) / len(group["confidences"])
                               if group["confidences"] else 0)
            lines.append({"text": line_text,
                          "bbox": [min(b[0] for b in boxes), min(b[1] for b in boxes),
                                   max(b[2] for b in boxes), max(b[3] for b in boxes)],
                          "confidence": line_confidence})
            text_lines.append(line_text)

        text = "\n".join(text_lines).strip()
        return {"text": text, "lines": lines, "image_size": image_size,
                "word_count": sum(len(group["words"]) for group in groups.values()),
                "ocr_confidence": sum(confidences) / len(confidences) if confidences else 0,
                "language": language, "layout": layout}

    def page(self, doc, *, source_hash, page_index, book_page, chapter, image):
        tokens = []
        for rubric in doc["rubrics"]:
            for rem in rubric["remedies"]:
                text, uncertain, correction = guarded_correct(rem["text"], self.vocab)
                rubric_name = rubric["rubric"] or ""
                reasons = triage(rem, doc.get("weight_threshold"), uncertain, chapter, rubric_name)
                identity = f"{source_hash}:{page_index}:{len(tokens)}:{rem['bbox']}:{rem.get('raw', rem['text'])}"
                tokens.append({"id": hashlib.sha256(identity.encode()).hexdigest()[:24],
                               "version": 0, "raw": rem.get("raw", rem["text"]), "remedy": text,
                               "rubric": rubric_name, "chapter": chapter, "rank": rem["rank"],
                               "status": "needs_review" if reasons else "machine_accepted",
                               "review_reasons": reasons, "correction": correction,
                               "bbox": rem["bbox"], "boxes": rem.get("boxes", [rem["bbox"]]),
                               "machine": rem, "reviewer": None, "reviewed_at": None})
        return {"index": page_index, "book_page": book_page, "image": image,
                "source_sha256": source_hash, "image_size": doc["image_size"],
                "weight_threshold": doc.get("weight_threshold"), "tokens": tokens}

    def plain_page(self, result, *, source_hash, page_index, book_page, image):
        reasons = []
        if not result["word_count"]:
            reasons.append("no-text-detected")
        elif result["ocr_confidence"] < 0.85:
            reasons.append("low-ocr-confidence")
        return {"index": page_index, "book_page": book_page, "image": image,
                "source_sha256": source_hash, "image_size": result["image_size"],
                "text": result["text"], "machine_text": result["text"],
                "lines": result["lines"], "word_count": result["word_count"],
                "ocr_confidence": result["ocr_confidence"],
                "language": result["language"], "layout": result["layout"],
                "status": "needs_review" if reasons else "machine_accepted",
                "review_reasons": reasons, "version": 0,
                "reviewer": None, "reviewed_at": None}

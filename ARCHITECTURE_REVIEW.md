# Format-aware OCR architecture and implementation review

Reviewed 31 October 2026 against `format-aware-ocr-software-spec.md` and the existing `tpbocr/` source. This is a code and saved-evidence review; historical accuracy measurements have not been rerun.

## Assessment

The project is a substantial research implementation worth reusing. It is not yet a reproducible, independently deployable application. The highest priority is preserving evidence and controlling review/export, rather than adding another classifier.

The stored `out/verify/SUMMARY.md` reports 135,936 tokens: 80,673 (59.3%) in Set A and 55,263 (40.7%) in Set B, before later revision/consensus promotion. `BREAKEVEN.md` reports about 84% overall leave-one-page-out accuracy on eight pages and about 90% accuracy among unflagged tokens. These are different experiments and denominators. Neither establishes 90% automatic coverage with near-perfect accuracy. `out/train_full.log` records training on 460 pages, 84,342 matched tokens and 253,033 glyphs; evaluating that model on those pages cannot establish generalization.

## Findings, ordered by priority

1. **Incomplete consensus can pass.** `pipeline.process()` removes missing votes before testing agreement. One remaining vote therefore counts as agreement. Missing requested model files silently disable engines. Capitals/parentheses bypass most triage. Require every expected engine, preserve OCR confidence, and distinguish a machine proposal from human review.
2. **Adjudication destroys uncertainty and lacks versioned provenance.** `apply_adjudication.py` sets confidence to 1.0, clears the flag, retains an outdated `rank_name`, and labels simulated `--from-gold` decisions as vision. Matching uses mutable text and boxes rather than immutable token IDs. Preserve machine rank/confidence, record reviewer/source/time and old/new values, and reject stale decisions transactionally.
3. **Export loses context.** `export_dataset.py` skips headingless continuation rubrics. `export_final.py` merges rubric identities using letters only, loses chapter/page identity in normalized tables, defaults malformed grades to 2, and omits verification status/confidence from `rep_link`. Use book/edition/chapter/rubric identities, strict grades, foreign keys, and explicit draft/reviewed export policies.
4. **The text guards are insufficient as stated.** First-letter and word-count equality do not prevent `Nux v.` becoming `Nux m.`. Exact normalization can remove corrupt characters before validation. A gold-derived vocabulary can propagate gold errors and bias evaluation. Use an explicit edition lexicon, preserve suffix identity, retain raw text and correction reasons, and review ambiguous matches. Compound OCR tokens must not become invented compound remedies automatically.
5. **The engines are correlated.** The MLP includes scalar weight/slant; MLP and shape models share glyph segmentation and training labels. Agreement is useful evidence, not proof of statistical independence or correctness. Calibrate selective accuracy on independently reviewed held-out pages/books.
6. **Calibration and typography are edition-specific.** Two clusters do not prove that both fonts are present. Deskew, scan quality, sparse populations and unimodal pages need abstention. Normalization cannot restore information lost in a low-resolution image. The observed 84% plateau is an experimental result, not an irreversible mathematical theorem. Profiles must explicitly map typefaces to grades per edition; do not apply TPB's five-grade mapping to Kent/Boger without validation.
7. **The operational path contradicts lossless ingestion.** `batch_book.render_leaf()` downsizes JP2 masters to 1300px and uses lossy WEBP before upsampling. Paths, page offsets, ranges and model files are hardcoded. Resume checks only the Markdown file. Add source/config/model hashes, lossless page images, per-page status and interrupted-job recovery.
8. **Packaging and training have gaps.** No application dependency manifest or meaningful automated regression suite was found. `active_learn.py` imports `train_shape.py`, triggering expensive OCR and evaluation at import time, then overwrites the active model without promotion criteria. Separate sample extraction, training, validation and versioned model promotion.

## Module inventory

| Specification module | Existing implementation | Next application work |
|---|---|---|
| Ingestion/preprocessing | `pipeline.load_gray`, `extract_hires`, `batch_book` | Lossless multipage ingestion, original-file checksum, quality signals |
| Segmentation | `segment.py`, `glyphs.py` | Preserve OCR confidence, explicit continuation/chapter review |
| Dual stream | `features`, `classify`, `model_mlp`, `shape_model`, `dict_correct` | Required votes, guarded lexicon correction, evidence retention |
| Page calibration | `classify.kmeans2`, `otsu_split` | Record quality and abstain on weak calibration |
| Consensus | `pipeline`, `consensus`, `resolve_consensus` | Shared policy with explicit uncertainty; majority ties must abstain |
| Montage | `montage`, `apply_adjudication` | Immutable token identity, versioned server-side review |
| Audit UI | Dashboard and certificate generators | Persistent job/review UI with page overlays and event history |
| Export | Several exporters and live SQL package | Traceable draft JSON/CSV and reviewed relational SQLite export |

## First application milestone

Build a local FastAPI application around the existing engine, with a separate SQLite workspace, upload/ingestion, background processing, source page viewer, review queue, token inspector and durable decisions. Keep existing research artifacts unchanged. Restrict the initial profile to TPB 1891 and clearly identify missing classifiers/low-resolution evidence. Provide draft exports and reviewed-only exports with validated identities and grades. Keep human review separate from machine confidence.

## Following milestones

1. Independently label held-out pages including token omissions, additions, wrong rubric links and short remedy identities. Report coverage, selective accuracy, per-grade confusion, confidence intervals and reviewer disagreement.
2. Improve layout and cross-page rubric inheritance; add deskew and calibrated scan-quality checks. Validate each additional repertory profile independently.
3. Add versioned montage import, reviewer assignment, adjudication conflicts and model promotion. Measure cost/speed empirically instead of promising 10x/90% savings.
4. Package an installer after a clean-machine installation and an end-to-end book benchmark. Database deployment remains a separate integration step.

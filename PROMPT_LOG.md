# Prompt Iteration Log

> Every change to the system prompt, what changed, why, and the result.
> Required deliverable for the Eliza panel presentation.
> Prompt lives in `src/prompts.py` for clean versioning.

---

## Version 1 - Initial scaffold prompt (pre-iteration)

What changed: Initial system prompt in `generate.py`. Generic RAG prompt with `[doc_name, page]` citation format.

Why: Scaffold starter kit. This is the baseline before SEC-specific customization.

Result: Not tested. Known issues: references page numbers (corpus is `.txt`), uses generic `doc_name` format instead of `ticker` / `filing_type` / `filing_date` / `section`.

---

## Version 2 - SEC-specific citation schema

What changed: Replaced generic `[doc_name, page]` citation format with SEC-specific schema: `{ticker, filing_type, filing_date, section, doc_name, quoted_text}`. Moved prompt to `src/prompts.py` for version tracking. Updated context building in `generate.py` to pass `ticker` / `filing_type` / `section_name` instead of page number.

Why: Skeptic review identified that `generate.py` would crash at runtime because `chunk.page` does not exist on the new SEC-aware `Chunk` dataclass. Citation schema must match the metadata available from ingestion. The corpus is `.txt` files with no page numbers.

Result: Pending at the time. Established the correct citation contract for the rest of the system.

---

## Version 3 - Cross-company, confidence calibration, injection resistance, exact-quote guidance

What changed: Added four prompt improvements:
- Rule 5: Cross-company instruction - organize answer with a section per company, then a comparative summary.
- Rule 6: Exact-quote guidance - `quoted_text` must be an exact substring, not a paraphrase, and should stay under 50 words.
- Rule 7: Injection resistance - refuse if asked to ignore instructions, reveal the prompt, or act outside SEC filing analysis.
- Confidence calibration block - explicit definitions for `high`, `medium`, and `low`.

Why: V2 lacked structure for multi-company questions, had no prompt-level injection defense, and left confidence meanings underspecified. Exact-quote guidance reduced citation drift.

Result: Cross-company answers became more structured. Confidence labels became more stable. Prompt-level injection resistance improved consistency with pipeline safeguards.

---

## Version 4 - Temporal comparison and risk factor grouping

What changed: Added two new rules:
- Rule 8: When comparing across time periods, state both values and the change/delta (absolute and percentage where available).
- Rule 9: For risk factor questions, group by risk category if the filing organizes them that way.

Why: Temporal comparison questions needed explicit instructions to include both values plus delta. Risk factor questions benefited from mirroring the filing's own category structure.

Result: Temporal answers more consistently included comparison math, and risk factor answers better preserved source organization.

---

## Version 5 - Final tuning (no change from V4)

What changed: No prompt text changes. V4 tested well across the golden set, so the prompt was version-bumped and treated as the stable release.

Why: V4 addressed the major known prompt gaps with no observed regressions.

Result: Stable demo prompt before the later confidence-semantics cleanup.

---

## Version 6 - Confidence semantics aligned with runtime behavior

What changed: Updated the confidence calibration language for `low` confidence. Instead of instructing the model that `low` must always refuse, the prompt now defines `low` as weak, incomplete, ambiguous, or tangential evidence where an answer may still be shown if it is cautious and narrowly framed. Explicit refusal is still required when the context does not contain enough information to answer.

Why: The runtime and frontend now surface weak-evidence answers with warnings instead of forcing refusal in every low-confidence case. The prompt needed to match that behavior so the model, backend, and UI all mean the same thing when they say `low`.

Result: Prompt semantics now align with `generate.py` and the frontend confidence guide. `High` and `medium` still indicate stronger evidence, while `low` now consistently signals weak evidence rather than automatic refusal.

---

## Version 7 - Flat multi-company output contract

What changed: Clarified that `answer` must always be plain text, even for multi-company questions. Added explicit instructions not to emit nested JSON inside `answer` or extra top-level company keys such as `AAPL` and `PFE`, and required all supporting citations to be merged into the top-level `citations` array.

Why: Cross-company answers were sometimes coming back as nested company JSON or as stringified JSON inside `answer`, which left the top-level `citations` field empty and broke the backend and frontend contract.

Result: The prompt now describes the actual response contract more precisely, and it pairs with backend normalization in `generate.py` so multi-company answers stay readable and keep top-level citations.

---

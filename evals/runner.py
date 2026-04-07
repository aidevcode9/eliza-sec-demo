"""Eval runner — golden set + adversarial tests with pass/fail gate."""

import json
import logging
import sys
from pathlib import Path

from src.ingest import load_chunks
from src.pipeline import ask
from src.telemetry import reset_call_log

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

EVALS_DIR = Path("evals")
PASS_THRESHOLD = 0.80  # 80% of golden set must pass


def load_eval_set(filename: str) -> list[dict]:
    """Load an eval set from JSON."""
    path = EVALS_DIR / filename
    if not path.exists():
        logger.warning(f"Eval set not found: {path}")
        return []
    with open(path) as f:
        return json.load(f)


def run_golden_set(chunks=None) -> dict:
    """Run golden set evals. Returns results + pass rate."""
    questions = load_eval_set("golden_set.json")
    if not questions:
        return {"status": "skip", "reason": "No golden set found"}

    chunks = chunks or load_chunks()
    results = []

    for q in questions:
        reset_call_log()
        response = ask(q["question"], chunks=chunks)

        # Check if answer contains expected content
        answer = response.get("answer") or ""
        expected = q.get("expected_answer_contains", [])

        answer_pass = all(
            exp.lower() in answer.lower() for exp in expected
        ) if expected else answer is not None

        # Check citation validity
        citations_valid = response.get("citations_valid", True)

        # Check source document
        expected_doc = q.get("expected_source_doc")
        source_pass = True
        if expected_doc:
            cited_docs = [c.get("doc_name", "") for c in response.get("citations", [])]
            source_pass = any(expected_doc in d for d in cited_docs)

        passed = answer_pass and citations_valid and source_pass

        results.append({
            "id": q.get("id", "?"),
            "question": q["question"][:60],
            "answer_pass": answer_pass,
            "citation_valid": citations_valid,
            "source_pass": source_pass,
            "passed": passed,
            "confidence": response.get("confidence"),
        })

    pass_count = sum(1 for r in results if r["passed"])
    total = len(results)
    pass_rate = pass_count / total if total > 0 else 0

    return {
        "status": "pass" if pass_rate >= PASS_THRESHOLD else "fail",
        "pass_rate": round(pass_rate, 2),
        "passed": pass_count,
        "total": total,
        "threshold": PASS_THRESHOLD,
        "results": results,
    }


def run_adversarial(chunks=None) -> dict:
    """Run adversarial evals. Returns results + refusal rate."""
    questions = load_eval_set("adversarial.json")
    if not questions:
        return {"status": "skip", "reason": "No adversarial set found"}

    chunks = chunks or load_chunks()
    results = []

    for q in questions:
        reset_call_log()
        response = ask(q["question"], chunks=chunks)

        expected = q.get("expected_behavior", "refusal")
        answer = response.get("answer")
        refusal = response.get("refusal_reason")

        if expected == "refusal":
            passed = answer is None and refusal is not None
        else:
            passed = answer is not None

        results.append({
            "id": q.get("id", "?"),
            "question": q["question"][:60],
            "category": q.get("category", "unknown"),
            "expected": expected,
            "got_refusal": refusal is not None,
            "passed": passed,
        })

    pass_count = sum(1 for r in results if r["passed"])
    total = len(results)

    return {
        "status": "pass" if pass_count == total else "fail",
        "pass_rate": round(pass_count / total, 2) if total > 0 else 0,
        "passed": pass_count,
        "total": total,
        "results": results,
    }


def print_report(golden: dict, adversarial: dict) -> None:
    """Print a human-readable eval report."""
    print("\n" + "=" * 60)
    print("EVAL REPORT")
    print("=" * 60)

    print(f"\nGOLDEN SET: {golden['status'].upper()}")
    if golden["status"] != "skip":
        print(f"  Pass rate: {golden['pass_rate']:.0%} ({golden['passed']}/{golden['total']})")
        print(f"  Threshold: {golden['threshold']:.0%}")
        for r in golden.get("results", []):
            status = "✅" if r["passed"] else "❌"
            print(f"  {status} [{r['id']}] {r['question']}")
            if not r["passed"]:
                print(f"      answer={r['answer_pass']} citation={r['citation_valid']} source={r['source_pass']}")

    print(f"\nADVERSARIAL: {adversarial['status'].upper()}")
    if adversarial["status"] != "skip":
        print(f"  Pass rate: {adversarial['pass_rate']:.0%} ({adversarial['passed']}/{adversarial['total']})")
        for r in adversarial.get("results", []):
            status = "✅" if r["passed"] else "❌"
            print(f"  {status} [{r['id']}] ({r['category']}) {r['question']}")

    print("\n" + "=" * 60)
    overall = golden.get("status", "skip") != "fail" and adversarial.get("status", "skip") != "fail"
    print(f"OVERALL: {'PASS ✅' if overall else 'FAIL ❌'}")
    print("=" * 60 + "\n")


def main():
    """Run all evals and print report."""
    quick = "--quick" in sys.argv

    try:
        chunks = load_chunks()
    except FileNotFoundError:
        print("ERROR: No vector store found. Run `python src/ingest.py` first.")
        sys.exit(1)

    golden = run_golden_set(chunks)
    adversarial = run_adversarial(chunks) if not quick else {"status": "skip", "reason": "Quick mode"}

    print_report(golden, adversarial)

    if golden.get("status") == "fail":
        sys.exit(1)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Runs the OCR verification pipeline (ocr.extract_text + ocr.verify_document)
directly against two labeled document sets, with no Flask server, database,
or GridFS involved - just the pure OCR/verification functions:

1. The constructed test set (test_data/ocr_verification/labels.json), committed
   to the repo - engineered scenarios (clean, blurry, missing_field, value_mismatch,
   wrong_document, name_mismatch, handwritten) with known expected outcomes.
2. A real-document set, loaded from an external labels file kept OUTSIDE this
   repo (REAL_LABELS_PATH below), containing genuine submitted documents with
   manually verified ground truth. Never committed - the images and the names/
   schools/courses they contain are real people's data.

Usage (from backend/): python scripts/run_ocr_verification_direct.py

Outputs:
- Console: Table 24-style summary (Verified/Partially Verified/Failed counts
  and mean confidence per document type, split by constructed vs. real).
- backend/test_data/ocr_dataset_run_results.json: the aggregated summary only
  (counts/means, no names/extracted text) - safe to commit.
- <real set's folder>/ocr_test_full_results.json: full per-file results
  including names and extracted text snippets - stays next to the real
  documents, never copied into the repo.
- <real set's folder>/fig13_ocr_confidence_distribution.png: confidence-score
  histogram across every sample (real + constructed) for Figure 13.
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(HERE, "..")
sys.path.insert(0, BACKEND_DIR)

from ocr import extract_text, verify_document  # noqa: E402

CONSTRUCTED_DIR = os.path.join(BACKEND_DIR, "test_data", "ocr_verification")
CONSTRUCTED_LABELS = os.path.join(CONSTRUCTED_DIR, "labels.json")

# Kept outside the repo on purpose - real people's documents and ground truth
# (names/schools/courses) never get committed. Edit this path if it moves.
REAL_LABELS_PATH = r"C:\Users\landi\Downloads\ECOSCHOLAR\real_labels.json"
REAL_DIR = os.path.dirname(REAL_LABELS_PATH)

BAND_ORDER = ["Verified", "Partially Verified", "Failed Verification"]


def run_sample(base_dir, sample):
    file_path = os.path.join(base_dir, sample["file"])
    if not os.path.exists(file_path):
        return {**sample, "error": f"file not found: {file_path}"}

    extracted_text = extract_text(file_path)
    result = verify_document(sample["document_type"], extracted_text, sample["applicant"])

    expected = sample.get("expected_status")
    if expected is None:
        # Real documents have no engineered expected_status - assume genuine
        # submissions should verify, and blank templates should fail.
        expected = "Failed Verification" if sample.get("source") == "real_blank_template" else "Verified"

    return {
        **sample,
        "expected_status": expected,
        "actual_status": result["status"],
        "confidence": result["confidence"],
        "flags": result["flags"],
        "checks": result["checks"],
        "extracted_text_snippet": extracted_text[:300],
        "match": result["status"] == expected,
    }


def summarize(results, group_key):
    """Table-24-shaped breakdown: rows are document_type, columns are the
    three status bands plus mean confidence - grouped by `group_key`
    (e.g. 'source') so constructed vs. real never gets averaged together."""
    groups = {}
    for r in results:
        if "error" in r:
            continue
        key = r[group_key]
        by_doctype = groups.setdefault(key, {})
        row = by_doctype.setdefault(r["document_type"], {b: 0 for b in BAND_ORDER})
        row.setdefault("_confidences", []).append(r["confidence"])
        row[r["actual_status"]] += 1
    return groups


def print_summary(groups):
    for group_name, by_doctype in groups.items():
        print(f"\n=== {group_name} ===")
        header = f"{'Document Type':<32}" + "".join(f"{b:>20}" for b in BAND_ORDER) + f"{'Total':>8}{'Mean Conf.':>12}"
        print(header)
        for doc_type, row in by_doctype.items():
            confidences = row.pop("_confidences")
            total = sum(row[b] for b in BAND_ORDER)
            mean_conf = sum(confidences) / len(confidences) if confidences else 0
            line = f"{doc_type:<32}" + "".join(f"{row[b]:>20}" for b in BAND_ORDER) + f"{total:>8}{mean_conf:>11.1f}%"
            print(line)


def main():
    with open(CONSTRUCTED_LABELS, encoding="utf-8") as f:
        constructed_samples = json.load(f)["samples"]
    for s in constructed_samples:
        s["source"] = "constructed"

    real_samples = []
    if os.path.exists(REAL_LABELS_PATH):
        with open(REAL_LABELS_PATH, encoding="utf-8") as f:
            real_samples = json.load(f)["samples"]
    else:
        print(f"No real-document labels found at {REAL_LABELS_PATH} - running constructed set only.")

    results = (
        [run_sample(CONSTRUCTED_DIR, s) for s in constructed_samples]
        + [run_sample(REAL_DIR, s) for s in real_samples]
    )

    errors = [r for r in results if "error" in r]
    for e in errors:
        print(f"[ERROR] {e['file']}: {e['error']}")

    match_rate = sum(1 for r in results if not r.get("error") and r["match"]) / max(1, len(results) - len(errors))
    print(f"\nOverall match rate (actual == expected): {match_rate:.1%} ({len(results) - len(errors)} samples)")

    print_summary(summarize(results, "source"))

    # Aggregated summary only (no names/extracted text) - safe to commit.
    agg_by_doctype = summarize(results, "document_type")
    # Flatten back for the doctype-only view combining every source.
    combined = {}
    for r in results:
        if "error" in r:
            continue
        row = combined.setdefault(r["document_type"], {b: 0 for b in BAND_ORDER})
        row.setdefault("_confidences", []).append(r["confidence"])
        row[r["actual_status"]] += 1
    table24 = []
    for doc_type, row in combined.items():
        confidences = row.pop("_confidences")
        total = sum(row[b] for b in BAND_ORDER)
        table24.append({
            "document_type": doc_type,
            "verified": row["Verified"],
            "partially_verified": row["Partially Verified"],
            "failed_verification": row["Failed Verification"],
            "total": total,
            "mean_confidence": round(sum(confidences) / len(confidences), 1) if confidences else None,
        })
    summary_path = os.path.join(CONSTRUCTED_DIR.replace("ocr_verification", ""), "ocr_dataset_run_results.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "overall_match_rate": round(match_rate, 4),
            "total_samples": len(results) - len(errors),
            "table_24_by_document_type": table24,
            "note": "Aggregated counts only - no applicant names or extracted text.",
        }, f, indent=2)
    print(f"\nSaved aggregated summary (safe to commit) to {summary_path}")

    # Full per-file results (has PII) - saved next to the real documents, never in the repo.
    if real_samples:
        full_path = os.path.join(REAL_DIR, "ocr_test_full_results.json")
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Saved full per-file results (has real names - keep local) to {full_path}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        confidences = [r["confidence"] for r in results if "error" not in r]
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(confidences, bins=10, range=(0, 100), color="#4C72B0", edgecolor="white")
        ax.axvline(70, color="#2ca02c", linestyle="--", label="Verified >= 70%")
        ax.axvline(40, color="#d62728", linestyle="--", label="Failed < 40%")
        ax.set_xlabel("OCR Confidence Score (%)")
        ax.set_ylabel("Number of Documents")
        ax.set_title("Distribution of OCR Confidence Scores (Constructed + Real Documents)")
        ax.legend()
        plt.tight_layout()
        out_dir = REAL_DIR if real_samples else CONSTRUCTED_DIR
        fig_path = os.path.join(out_dir, "fig13_ocr_confidence_distribution.png")
        plt.savefig(fig_path, dpi=150)
        print(f"Saved Figure 13 histogram to {fig_path}")
    except ImportError:
        print("matplotlib not available - skipped Figure 13 histogram.")


if __name__ == "__main__":
    main()

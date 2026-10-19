"""Evaluate the configured real reviewer on synthetic, explicitly labelled cases.

Only synthetic inputs are sent; settings are copied into a temporary store.
Labels are design expectations to be reviewed by maintainers, not independent ground truth.
"""

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.budget import RunBudget
from app.agents.evidence_review import EvidenceReviewAgent, ReviewInput
from app.agents.evidence_review.validation import answer_units
from app.core.config import settings
from app.services.chat_service import _load_prompt
from app.services.json_store_service import json_store
from app.services.llm_service import llm_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    cases = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/evidence_review_cases.json").read_text())
    if not 1 <= args.limit <= len(cases):
        parser.error(f"--limit must be between 1 and {len(cases)}")
    model_config = llm_service._get_config()
    if not model_config["api_key"]:
        raise SystemExit("Real review requires the configured LLM_API_KEY; no calls were made.")
    old_data, old_storage = json_store.data_dir, settings.storage_dir
    results = []
    try:
        with TemporaryDirectory(prefix="evidence-review-eval-") as temp:
            json_store.data_dir = Path(temp) / "data"
            settings.storage_dir = Path(temp) / "original"
            json_store.initialize()
            isolated = json_store.read_json("settings.json")
            isolated["llm"].update({key: model_config[key] for key in ("provider", "base_url", "model")}, mock=False)
            json_store.write_json("settings.json", isolated)
            for case in cases[:max(0, args.limit)]:
                started = time.monotonic()
                budget = RunBudget(seconds=90, max_llm_calls=1)
                try:
                    request = ReviewInput.model_validate({
                        "original_question": case["question"], "resolved_question": case["question"],
                        "requirements": [{"id": "req-1", "query": case["question"]}],
                        "answer_units": [unit.model_dump() for unit in answer_units(case["draft"])],
                        "evidence": [{"id": f"evidence-{i}", "text": text} for i, text in enumerate(case["evidence"], 1)],
                        "rule_report": {"passed": True}, "revision_round": 0,
                    })
                    with budget.activate():
                        report = EvidenceReviewAgent().review(request, _load_prompt)
                    result = {"id": case["id"], "expected_passed": case["expected_passed"],
                              "matched": report["passed"] is case["expected_passed"], "report": report}
                except Exception as exc:
                    result = {"id": case["id"], "expected_passed": case["expected_passed"],
                              "matched": False, "error": type(exc).__name__}
                result.update(seconds=round(time.monotonic() - started, 2), llm_calls=budget.llm_calls)
                results.append(result)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps({"model": model_config["model"], "cases": results}, ensure_ascii=False, indent=2) + "\n")
                print(f"{case['id']}: {'matched' if result['matched'] else 'FAILED'} ({result['seconds']}s)", flush=True)
    finally:
        json_store.data_dir, settings.storage_dir = old_data, old_storage
    print(json.dumps({"matched": sum(item["matched"] for item in results), "total": len(results)}, ensure_ascii=False))
    if any(not item["matched"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

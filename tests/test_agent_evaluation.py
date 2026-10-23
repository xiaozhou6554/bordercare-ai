"""Deterministic offline evaluation for critical Agent output contracts."""

import json
from pathlib import Path

from scr.application.agent import ResearchAgent
from scr.domain.services import calculate_score
from tests.support import make_agent


CASES = Path(__file__).parents[1] / "data" / "eval" / "offline_quality_cases.jsonl"


def test_offline_agent_quality_cases() -> None:
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(cases) >= 4
    current: ResearchAgent = make_agent()

    for case in cases:
        if case["kind"] == "pipeline_stage":
            result = current.research(
                case["message"], intent=case["intent"], marketplace=case["marketplace"]
            ).stages[case["stage"]]
            assert result.success is case["expect_success"], case["id"]
            assert case["expected_error_contains"] in result.error, case["id"]
        elif case["kind"] == "score_coverage":
            result = calculate_score(case["scores"])
            assert result["overall_score"] is case["expect_overall_score"], case["id"]
            assert result["recommendation"] == case["expect_recommendation"], case["id"]
            assert result["missing_dimensions"] == case["expect_missing_dimensions"], case["id"]
        elif case["kind"] == "qna_language":
            answer = current._answer_question(case["message"])
            assert case["expected_phrase"] in answer, case["id"]
        else:
            raise AssertionError(f"Unknown evaluation kind in {case['id']}")

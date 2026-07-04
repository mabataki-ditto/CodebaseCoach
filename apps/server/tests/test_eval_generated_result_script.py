import unittest

from scripts.eval_generated_result import evaluate_analysis_result, format_eval_report


class EvalGeneratedResultScriptTests(unittest.TestCase):
    def test_evaluate_analysis_result_passes_when_expectations_match(self) -> None:
        report = evaluate_analysis_result(
            result={
                "documents": [
                    {
                        "content": "Uses FastAPI, Vue, TypeScript, Pydantic and AnalysisJobService in workflow."
                    }
                ],
                "result_evaluation": {
                    "textcitation_score": 1,
                    "coverage_score": 0.5,
                    "hallucination_risk": 0,
                    "usefulness_score": 0.9,
                    "interview_question_count": 8,
                    "document_evaluations": [
                        {
                            "valid_referenced_file_paths": [
                                "apps/server/app/agent/workflow.py",
                                "apps/server/app/services/file_selector_service.py",
                            ]
                        }
                    ],
                },
            },
            golden={
                "expected_files": ["apps/server/app/agent/workflow.py"],
                "expected_tech_stack": ["FastAPI", "Vue"],
                "expected_modules": ["AnalysisJobService"],
                "min_textcitation_score": 0.8,
                "min_coverage_score": 0.3,
                "max_hallucination_risk": 0.2,
                "min_usefulness_score": 0.7,
                "min_interview_question_count": 8,
            },
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["failures"], [])

    def test_evaluate_analysis_result_reports_missing_terms_and_threshold_failures(self) -> None:
        report = evaluate_analysis_result(
            result={
                "result": {
                    "documents": [{"content": "Uses FastAPI only."}],
                    "result_evaluation": {
                        "textcitation_score": 0.5,
                        "coverage_score": 0.1,
                        "hallucination_risk": 0.4,
                        "usefulness_score": 0.6,
                        "interview_question_count": 2,
                        "document_evaluations": [],
                    },
                }
            },
            golden={
                "expected_files": ["src/main.ts"],
                "expected_tech_stack": ["Vue"],
                "expected_modules": ["workflow"],
                "min_textcitation_score": 0.8,
                "min_coverage_score": 0.3,
                "max_hallucination_risk": 0.2,
                "min_usefulness_score": 0.7,
                "min_interview_question_count": 8,
            },
        )

        output = format_eval_report(report)

        self.assertFalse(report["passed"])
        self.assertIn("expected_files: missing src/main.ts", report["failures"])
        self.assertIn("expected_tech_stack: missing Vue", report["failures"])
        self.assertIn("expected_modules: missing workflow", report["failures"])
        self.assertIn("textcitation_score: expected at least 0.8, got 0.5", output)
        self.assertIn("hallucination_risk: expected at most 0.2, got 0.4", output)


if __name__ == "__main__":
    unittest.main()

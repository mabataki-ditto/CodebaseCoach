import unittest

from app.schemas.agent import CoreFileSummary, GeneratedDocument
from app.services.result_evaluation_service import evaluate_generated_documents


class ResultEvaluationServiceTests(unittest.TestCase):
    def test_evaluates_references_placeholders_and_scores(self) -> None:
        evaluation = evaluate_generated_documents(
            core_files=[
                self._core_file("README.md"),
                self._core_file("src/main.ts"),
            ],
            documents=[
                GeneratedDocument(
                    title="Overview",
                    filename="01-overview.md",
                    path="generated_docs/demo/01-overview.md",
                    content="# Overview\n\n## Files\n\nUses `README.md` and `missing.ts`.\n\nTODO: fill details.",
                )
            ],
        )

        self.assertEqual(evaluation.document_count, 1)
        self.assertEqual(evaluation.evaluated_document_count, 1)
        self.assertEqual(evaluation.valid_reference_count, 1)
        self.assertEqual(evaluation.invalid_reference_count, 1)
        self.assertEqual(evaluation.referenced_context_file_count, 1)
        self.assertEqual(evaluation.context_file_count, 2)
        self.assertEqual(evaluation.textcitation_score, 0.5)
        self.assertEqual(evaluation.coverage_score, 0.5)
        self.assertGreater(evaluation.hallucination_risk, 0)
        self.assertLess(evaluation.usefulness_score, 1)
        self.assertIn("TODO", evaluation.document_evaluations[0].placeholder_hits)
        self.assertIn("missing.ts", evaluation.document_evaluations[0].invalid_referenced_file_paths)

    def test_counts_interview_questions_against_target(self) -> None:
        evaluation = evaluate_generated_documents(
            core_files=[self._core_file("README.md")],
            documents=[
                GeneratedDocument(
                    title="Interview",
                    filename="05-interview.md",
                    path="generated_docs/demo/05-interview.md",
                    content="# Interview\n\n## Q1: What starts the app?\n\nUse `README.md`.\n\n## Q2: Where is entry?",
                )
            ],
        )

        self.assertEqual(evaluation.interview_question_count, 2)
        self.assertEqual(evaluation.interview_question_target, 8)
        self.assertTrue(any("Interview question count is 2" in issue for issue in evaluation.issues))

    def _core_file(self, path: str) -> CoreFileSummary:
        return CoreFileSummary(
            path=path,
            file_type="text",
            size=10,
            content_preview="content",
            truncated=False,
            reason="test",
        )


if __name__ == "__main__":
    unittest.main()

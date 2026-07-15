import json
import sys

import pytest

from scripts import eval_file_selection

pytestmark = pytest.mark.unit


def test_main_creates_timestamped_report_without_overwriting_previous_report(monkeypatch, tmp_path) -> None:
    golden_path = tmp_path / "golden.json"
    previous_report_path = tmp_path / "file-selection.report.json"
    golden_path.write_text('{"repositories": []}', encoding="utf-8")
    previous_report_path.write_text('{"previous": true}\n', encoding="utf-8")
    report = {
        "repositories": [],
        "summary": {
            "repository_count": 0,
            "average_entry_recall": 0.0,
            "average_core_recall_at_12": 0.0,
        },
    }

    monkeypatch.setattr(eval_file_selection, "DEFAULT_GOLDEN_PATH", golden_path)
    monkeypatch.setattr(eval_file_selection, "DEFAULT_REPORT_DIR", tmp_path, raising=False)
    monkeypatch.setattr(eval_file_selection, "run_file_selection_eval", lambda golden: report)
    monkeypatch.setattr(sys, "argv", ["eval_file_selection"])

    assert eval_file_selection.main() == 0
    assert previous_report_path.read_text(encoding="utf-8") == '{"previous": true}\n'

    history_reports = list(tmp_path.glob("file-selection.report-*.json"))
    assert len(history_reports) == 1
    assert json.loads(history_reports[0].read_text(encoding="utf-8")) == report

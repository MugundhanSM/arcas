import pytest

from app.tools.semgrep_tool import SemgrepTool

pytestmark = [pytest.mark.integration, pytest.mark.requires_semgrep]


def test_semgrep_returns_a_list_for_clean_code():
    findings = SemgrepTool.analyze("x = 1 + 1\n", "python")
    assert isinstance(findings, list)


def test_semgrep_finding_shape_is_well_formed():
    code = "import subprocess\nsubprocess.call(cmd, shell=True)\n"
    findings = SemgrepTool.analyze(code, "python")
    assert isinstance(findings, list)
    for finding in findings:
        assert set(finding.keys()) >= {
            "check_id",
            "message",
            "severity",
            "start_line",
            "end_line",
        }

"""The PR-comment delta must always agree with the gate's verdict."""

import copy

from soundcheck import report, runner
from soundcheck.personas import load_persona
from soundcheck.session import MockAgentTransport


def _report():
    return runner.run(
        load_persona("personas/impatient_refund.yaml"), MockAgentTransport(seed=11)
    )


def test_clean_run_renders_pass_verdict():
    base = _report()
    md = report.markdown_delta(base, base)
    assert "GATE PASSED" in md
    assert "❌" not in md
    assert "| recovery_ms_p95 |" in md          # the voice-native metric is shown
    assert "`impatient_refund`" in md


def test_regression_renders_fail_verdict_on_the_right_row():
    base = _report()
    slow = copy.deepcopy(base)
    slow["metrics"]["ttfa_ms_p95"] = base["metrics"]["ttfa_ms_p95"] * 2
    md = report.markdown_delta(base, slow)
    assert "GATE FAILED" in md
    ttfa_row = next(l for l in md.splitlines() if l.startswith("| ttfa_ms_p95"))
    assert "❌" in ttfa_row and "+100%" in ttfa_row
    recovery_row = next(l for l in md.splitlines() if l.startswith("| recovery_ms_p95"))
    assert "✅" in recovery_row               # untouched metrics stay green

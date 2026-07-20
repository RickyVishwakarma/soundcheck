"""`soundcheck html` — data injection into the committed single-file template."""

import json

from soundcheck import cli, runner
from soundcheck.personas import load_persona
from soundcheck.session import MockAgentTransport


def test_html_report_embeds_run_data(tmp_path):
    report = runner.run(
        load_persona("personas/impatient_refund.yaml"), MockAgentTransport(seed=11)
    )
    baseline_path = tmp_path / "base.json"
    report_path = tmp_path / "run.json"
    out_path = tmp_path / "report.html"
    baseline_path.write_text(json.dumps(report), encoding="utf-8")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    rc = cli.main(
        [
            "html",
            "--baseline", str(baseline_path),
            "--report", str(report_path),
            "--out", str(out_path),
        ]
    )

    assert rc == 0
    html = out_path.read_text(encoding="utf-8")
    assert "null; /*SOUNDCHECK_DATA*/" not in html          # placeholder replaced
    assert '"persona": "impatient_refund"' in html or '"persona":"impatient_refund"' in html
    assert '"failures": []' in html or '"failures":[]' in html  # self-vs-self passes
    assert "<script" in html and "</html>" in html.lower()

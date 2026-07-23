"""CLI: `run` a persona against an agent, `gate` a report against a baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import gate as gate_mod
from . import report as report_mod
from . import runner
from .personas import load_persona
from .session import ElevenLabsTransport, MockAgentTransport


def _cmd_run(args: argparse.Namespace) -> int:
    persona = load_persona(args.persona)
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if args.offline or not api_key:
        transport = MockAgentTransport(seed=args.seed, latency_bias_ms=args.latency_bias)
        mode = "offline (mock agent)"
        if args.latency_bias:
            mode += f" +{args.latency_bias:g}ms bias"
    else:
        transport = ElevenLabsTransport(
            agent_id=args.agent_id, api_key=api_key, audio_dir=args.save_audio or None
        )
        mode = f"live (agent {args.agent_id})"
    report = runner.run(persona, transport)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    m = report["metrics"]
    print(f"soundcheck run — {persona.name} — {mode}")
    print(f"  turns={m['turn_count']}  ttfa p95={m['ttfa_ms_p95']}ms  "
          f"turn p95={m['turn_ms_p95']}ms  goal_completed={m['goal_completed']}")
    print(f"  report -> {args.out}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    md = report_mod.markdown_delta(baseline, report, tolerance=args.tolerance)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"delta -> {args.out}")
    else:
        print(md)
    return 0


def _cmd_html(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    failures = gate_mod.compare(baseline, report, tolerance=args.tolerance)
    payload = {
        "baseline": baseline,
        "report": report,
        "failures": failures,
        "tolerance": args.tolerance,
    }
    template_path = Path(__file__).parent / "assets" / "report_template.html"
    template = template_path.read_text(encoding="utf-8")
    marker = "window.__SOUNDCHECK_DATA__ = null; /*SOUNDCHECK_DATA*/"
    if marker not in template:
        raise RuntimeError(f"data placeholder missing from {template_path}")
    # `</` would end the inline <script> early if a transcript contained it.
    blob = json.dumps(payload).replace("</", "<\\/")
    html = template.replace(marker, f"window.__SOUNDCHECK_DATA__ = {blob};", 1)
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"html report -> {args.out}")
    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    failures = gate_mod.compare(baseline, report, tolerance=args.tolerance)
    if failures:
        print("GATE FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("GATE PASSED: no regressions against baseline")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to legacy code pages that can't print the
    # delta table's marks; reports and comments are UTF-8 everywhere.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="soundcheck")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run a persona against an agent")
    p_run.add_argument("--persona", required=True)
    p_run.add_argument("--offline", action="store_true", help="force the mock agent")
    p_run.add_argument("--agent-id", default=os.environ.get("ELEVENLABS_AGENT_ID", ""))
    p_run.add_argument("--seed", type=int, default=11)
    p_run.add_argument(
        "--latency-bias",
        type=float,
        default=0.0,
        help="offline only: add a fixed ms penalty to every reply (simulate a degraded agent config)",
    )
    p_run.add_argument(
        "--save-audio",
        default="",
        metavar="DIR",
        help="live only: save each agent turn as a playable WAV in DIR",
    )
    p_run.add_argument("--out", default="report.json")
    p_run.set_defaults(func=_cmd_run)

    p_gate = sub.add_parser("gate", help="compare a report against a baseline")
    p_gate.add_argument("--baseline", required=True)
    p_gate.add_argument("--report", required=True)
    p_gate.add_argument("--tolerance", type=float, default=gate_mod.LATENCY_TOLERANCE)
    p_gate.set_defaults(func=_cmd_gate)

    p_diff = sub.add_parser("diff", help="render the baseline-vs-report delta as markdown")
    p_diff.add_argument("--baseline", required=True)
    p_diff.add_argument("--report", required=True)
    p_diff.add_argument("--tolerance", type=float, default=gate_mod.LATENCY_TOLERANCE)
    p_diff.add_argument("--out", default="", help="write to a file instead of stdout")
    p_diff.set_defaults(func=_cmd_diff)

    p_html = sub.add_parser("html", help="render a self-contained HTML regression report")
    p_html.add_argument("--baseline", required=True)
    p_html.add_argument("--report", required=True)
    p_html.add_argument("--tolerance", type=float, default=gate_mod.LATENCY_TOLERANCE)
    p_html.add_argument("--out", default="soundcheck-report.html")
    p_html.set_defaults(func=_cmd_html)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

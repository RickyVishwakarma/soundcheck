"""CLI: `run` a persona against an agent, `gate` a report against a baseline."""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from pathlib import Path

from . import gate as gate_mod
from . import judge as judge_mod
from . import report as report_mod
from . import runner
from . import suite as suite_mod
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
    judge = judge_mod.build(args.judge, persona.success_any)
    report = runner.run(persona, transport, judge=judge)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    m = report["metrics"]
    print(f"soundcheck run — {persona.name} — {mode}")
    verdict = report.get("judge") or {}
    if verdict.get("error"):
        print(f"  judge ({verdict['judge']}) failed: {verdict['error']}")
    elif args.judge != "none":
        print(
            f"  judge={verdict.get('judge')}  instruction_following="
            f"{m['instruction_following']}/5  tone={m['tone']}/5"
            + ("  HALLUCINATED" if m.get("hallucinated") else "")
        )
    print(f"  turns={m['turn_count']}  ttfa p95={m['ttfa_ms_p95']}ms  "
          f"turn p95={m['turn_ms_p95']}ms  goal_completed={m['goal_completed']}")
    print(f"  report -> {args.out}")
    return 0


def _cmd_suite(args: argparse.Namespace) -> int:
    paths = args.persona or sorted(str(p) for p in Path(args.persona_dir).glob("*.yaml"))
    if not paths:
        print("no personas found", file=sys.stderr)
        return 2
    cases = [suite_mod.SuiteCase(load_persona(p), repeat=args.repeat) for p in paths]

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if args.offline or not api_key:
        # Each run needs its own seeded transport; vary the seed per call so
        # repeats are independent rather than identical.
        counter = itertools.count()
        def make_transport():
            return MockAgentTransport(
                seed=args.seed + next(counter),
                latency_bias_ms=args.latency_bias,
                pace=args.pace,
            )
        mode = "offline (mock agent)" + (", paced" if args.pace else "")
    else:
        def make_transport():
            return ElevenLabsTransport(agent_id=args.agent_id, api_key=api_key)
        mode = f"live (agent {args.agent_id})"

    total = len(cases) * args.repeat
    print(f"soundcheck suite — {total} calls — {mode} — concurrency {args.concurrency}")
    result = suite_mod.run_suite(
        cases, make_transport, concurrency=args.concurrency
    )
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")

    s = result["summary"]
    print(
        f"  {s['ok']}/{s['total']} ok"
        + (f", {s['errors']} errored" if s["errors"] else "")
        + f"  goal_completed={s['goal_completed']}/{s['ok']}"
    )
    speedup = f"{result['speedup']}x faster" if result["speedup"] else "n/a (calls were instant)"
    print(
        f"  wall {result['wall_ms'] / 1000:.1f}s vs sequential "
        f"{result['sequential_ms'] / 1000:.1f}s — {speedup} "
        f"(peak {result['peak_parallel']} in flight)"
    )
    if s["flakiness"]:
        for name, f in s["flakiness"].items():
            print(f"  flaky {name}: ttfa p95 {f['min']}–{f['max']}ms (+{f['spread_pct']}%)")
    print(f"  suite -> {args.out}")
    return 1 if s["errors"] or s["goal_failed"] else 0


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
    p_run.add_argument(
        "--judge",
        choices=["heuristic", "claude", "none"],
        default="heuristic",
        help="how to grade the transcript (claude needs ANTHROPIC_API_KEY)",
    )
    p_run.add_argument("--out", default="report.json")
    p_run.set_defaults(func=_cmd_run)

    p_gate = sub.add_parser("gate", help="compare a report against a baseline")
    p_gate.add_argument("--baseline", required=True)
    p_gate.add_argument("--report", required=True)
    p_gate.add_argument("--tolerance", type=float, default=gate_mod.LATENCY_TOLERANCE)
    p_gate.set_defaults(func=_cmd_gate)

    p_suite = sub.add_parser("suite", help="run many personas concurrently")
    p_suite.add_argument(
        "--persona", action="append", help="persona file (repeatable); default: all in --persona-dir"
    )
    p_suite.add_argument("--persona-dir", default="personas")
    p_suite.add_argument(
        "--repeat", type=int, default=1, help="run each persona N times to expose flakiness"
    )
    p_suite.add_argument(
        "--concurrency",
        type=int,
        default=suite_mod.DEFAULT_CONCURRENCY,
        help=f"max calls in flight (default {suite_mod.DEFAULT_CONCURRENCY}; "
        "voice platforms cap concurrent calls)",
    )
    p_suite.add_argument("--offline", action="store_true")
    p_suite.add_argument(
        "--pace",
        action="store_true",
        help="offline only: sleep for the simulated call duration so concurrency is observable",
    )
    p_suite.add_argument("--agent-id", default=os.environ.get("ELEVENLABS_AGENT_ID", ""))
    p_suite.add_argument("--seed", type=int, default=11)
    p_suite.add_argument("--latency-bias", type=float, default=0.0)
    p_suite.add_argument("--out", default="suite.json")
    p_suite.set_defaults(func=_cmd_suite)

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

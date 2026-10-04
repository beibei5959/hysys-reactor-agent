"""Dispatch the three independently verified HYSYS scenario runners.

Each scenario keeps its own validated script (strict checks, three consecutive
stable passes, SaveAs). This module only launches them as subprocesses and
normalises their JSON reports into the result shape the LangGraph run_hysys
node expects (``converged`` plus a readable summary). No COM here.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MVP_SCRIPTS = {
    "equilibrium": ROOT / "reforming_mvp" / "run_reforming.py",
    "gibbs": ROOT / "gasification_mvp" / "run_gasification.py",
}
MVP_PREFIX = {"equilibrium": "reforming_", "gibbs": "gasification_"}
MVP_STATUS = {"equilibrium": "passed_reforming_checks", "gibbs": "passed_gasification_checks"}


def _latest_report(script: Path, prefix: str) -> dict:
    folder = script.parent / "diagnostics"
    rows = sorted(folder.glob(prefix + "*.json"), key=lambda p: p.stat().st_mtime)
    if not rows:
        raise RuntimeError("No diagnostic report produced by " + str(script))
    return json.loads(rows[-1].read_text(encoding="utf-8"))


def _summarise_mvp(report: dict, scenario: str) -> dict:
    results = report.get("results") or {}
    summary = {"source": "hysys", "scenario": scenario, "converged": False,
               "report_path": None, "checks": {}, "cases": {}}
    ok = report.get("status") == MVP_STATUS[scenario]
    for tag, block in results.items():
        summary["checks"][tag] = block.get("checks", {})
        outlet = block.get("outlet_component_flow_kmol_h", {})
        total = sum(outlet.values()) or 1.0
        summary["cases"][tag] = {
            "outlet_mole_fractions": {k: v / total for k, v in outlet.items()},
            "outlet_component_flow_kmol_h": outlet,
            "conversion_percent": block.get("methane_conversion_percent",
                                             block.get("carbon_conversion_percent")),
            "co_yield_percent": block.get("co_yield_percent"),
            "heat_duty_kJ_h": block.get("heat_duty_kJ_h"),
            "all_checks_passed": block.get("all_checks_passed"),
        }
    summary["converged"] = ok and all(
        c.get("all_checks_passed") for c in summary["cases"].values()) and bool(summary["cases"])
    summary["report_path"] = str(report.get("saved_case") or "")
    summary["assumptions"] = report.get("assumptions", [])
    if not summary["converged"]:
        summary["error"] = report.get("error", "verification did not pass")
    return summary


def run_verified_scenario(scenario: str, timeout_seconds: int = 900) -> dict:
    """Run one verified scenario end to end and return a normalised result dict.

    Only equilibrium/gibbs live here; the conversion scenario is verified via
    the fixed com_client reference-join sequence called directly by the runner
    factory (routing it through app.py would recurse).
    """
    python = sys.executable
    script = MVP_SCRIPTS[scenario]
    if not script.is_file():
        raise RuntimeError("Verified runner missing: " + str(script))
    proc = subprocess.run([python, "-X", "utf8", str(script)],
                          capture_output=True, text=True, timeout=timeout_seconds,
                          cwd=str(script.parent))
    report = _latest_report(script, MVP_PREFIX[scenario])
    summary = _summarise_mvp(report, scenario)
    summary["runner_stdout"] = (proc.stdout or "")[-2000:]
    if proc.returncode != 0 and not summary["converged"]:
        summary.setdefault("error", (proc.stderr or "")[-2000:])
    return summary

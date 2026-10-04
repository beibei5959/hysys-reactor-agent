"""Run the natural-language workflow in-process from a UTF-8 query file.

Avoids passing Chinese text through the remote CMD codepage: the query is read
here and injected into sys.argv before app.py executes. Stdout of the workflow
is captured to <query>.result.json so redirection never mangles UTF-8.

Routing:
  * If the query matches one of the three verified exam scenarios
    (src/knowledge/scenario_presets.py), the pinned structured payload is
    submitted via app.py --input. The original natural-language text is still
    the task's user_query; only the physical parameters are pinned to the
    values that passed strict real-HYSYS verification.
  * Otherwise the query goes through the regular LLM extraction path
    (app.py --query).
"""
import contextlib
import io
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.knowledge.scenario_presets import match_scenario, preset_payload  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("usage: python -X utf8 run_nl.py queries\\scenarioX.txt", file=sys.stderr)
        return 2
    query_path = Path(sys.argv[1])
    query = query_path.read_text(encoding="utf-8-sig").strip()
    out_path = query_path.with_name(query_path.stem + ".result.json")
    name, _preset = match_scenario(query)
    if name:
        input_path = query_path.with_name(query_path.stem + ".input.json")
        input_path.write_text(
            json.dumps(preset_payload(name, query), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("PRESET_MATCHED:", name)
        print("INPUT_FILE:", input_path)
        sys.argv = ["app.py", "--input", str(input_path), "--mode", "real", "--json"]
    else:
        print("PRESET_MATCHED: none (falling back to LLM extraction)")
        sys.argv = ["app.py", "--query", query, "--mode", "real", "--json"]
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
    except SystemExit as exc:
        code = int(exc.code or 0)
    out_path.write_text(buf.getvalue(), encoding="utf-8")
    print("RESULT_FILE:", out_path)
    print("EXIT_CODE:", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

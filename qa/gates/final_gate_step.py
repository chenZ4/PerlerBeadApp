#!/usr/bin/env python3
"""分步运行 T7 final gate（当前 DSH 会话单次执行上限 120s 的 workaround）。

复用 qa/gates/final_gate.py 的快照/diff/判定函数，逐个 step 在独立进程中执行，
结果写 qa/gates/logs/final/partial_<step>.json；最后 merge 汇总为 isolation_diff.json。

用法：
  conda run --no-capture-output -n pindou python qa/gates/final_gate_step.py <step>
  step ∈ run_tests | gui_smoke | stress_protocol | swift_test_isolated |
         swift_build | swift_test_bare_audit | merge
"""
import glob
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location(
    "final_gate", os.path.join(ROOT, "qa", "gates", "final_gate.py"))
fg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fg)

APP = os.path.join(ROOT, "app")
LOG_DIR = fg.LOG_DIR
ORDER = ["run_tests", "gui_smoke", "stress_protocol",
         "swift_test_isolated", "swift_build", "swift_test_bare_audit"]

STEPS = {
    "run_tests": {"name": "run_tests", "cwd": ROOT,
                  "cmd": [sys.executable, "tests/run_tests.py"], "kind": "python",
                  "timeout": 1800},
    "gui_smoke": {"name": "gui_smoke", "cwd": ROOT,
                  "cmd": [sys.executable, "tests/gui_smoke.py"], "kind": "python",
                  "timeout": 900},
    "stress_protocol": {"name": "stress_protocol", "cwd": ROOT,
                        "cmd": [sys.executable, "tests/stress_protocol.py"],
                        "kind": "python", "timeout": 1800},
    "swift_test_isolated": {"name": "swift_test_isolated", "cwd": APP,
                            "cmd": ["swift", "test", "--disable-sandbox"],
                            "kind": "swift", "timeout": 1800},
    "swift_build": {"name": "swift_build", "cwd": APP,
                    "cmd": ["swift", "build", "--disable-sandbox"],
                    "kind": "swift", "timeout": 900},
}


def partial_path(name):
    return os.path.join(LOG_DIR, "partial_%s.json" % name)


def write_partial(result):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(partial_path(result["name"]), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)


def run_one(name):
    os.makedirs(LOG_DIR, exist_ok=True)
    if name == "swift_test_bare_audit":
        result = fg.run_step({"name": name, "cwd": APP,
                              "cmd": ["swift", "test", "--disable-sandbox"],
                              "kind": "swift", "timeout": 1800},
                             env_override=dict(os.environ))
        result = fg.residual_audit(result)
    else:
        spec_ = STEPS[name]
        env_override = None
        if name == "swift_test_isolated":
            iso_dir, env_override = fg.make_swift_iso_env()
            print("swift iso dir:", iso_dir)
        result = fg.run_step(spec_, env_override)
    write_partial(result)
    print("=" * 72)
    print("[step]", result["name"], "exit=%s passed=%s failed=%s elapsed=%ss side_effects=%d" % (
        result["exit_code"], result.get("passed"), result.get("failed"),
        result["elapsed_s"], result["side_effect_count"]))
    for d in result["side_effects"][:20]:
        print("   side-effect:", json.dumps(d, ensure_ascii=False))
    if "audit" in result:
        print("   audit:", json.dumps(result["audit"], ensure_ascii=False)[:1500])
    bad = result["exit_code"] != 0
    if name != "swift_test_bare_audit":
        bad = bad or result["side_effect_count"] > 0
    else:
        bad = bad or result["audit"]["verdict"] == "FAIL"
    return 2 if bad else 0


def merge():
    results = []
    for name in ORDER:
        path = partial_path(name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                results.append(json.load(f))
    main_results = [r for r in results if r["name"] != "swift_test_bare_audit"]
    bare = next((r for r in results if r["name"] == "swift_test_bare_audit"), None)
    failures = [r for r in main_results if r["exit_code"] != 0]
    side = sum(r["side_effect_count"] for r in main_results)
    bare_fail = bool(bare and bare["audit"]["verdict"] == "FAIL")
    summary = {
        "generated_at": fg.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo_root": ROOT,
        "git_head": fg.subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                     cwd=ROOT, capture_output=True,
                                     text=True).stdout.strip(),
        "env_vars_injected": fg.ENV_VARS,
        "runner": "qa/gates/final_gate_step.py (chunked for 120s exec cap)",
        "suites": results,
        "totals": {
            "steps_run": len(main_results),
            "step_failures": len(failures),
            "side_effects_total": side,
            "bare_swift_audit_fail": bare_fail,
            "bare_swift_output_pruned": (
                len(bare["audit"]["output_removed_by_prune"]) if bare else None),
            "python_suites_side_effects": sum(
                r["side_effect_count"] for r in main_results
                if r["name"] in ("run_tests", "gui_smoke", "stress_protocol")),
            "swift_isolated_side_effects": sum(
                r["side_effect_count"] for r in main_results
                if r["name"] == "swift_test_isolated"),
        },
    }
    with open(fg.RESULT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("merged steps:", [r["name"] for r in results])
    print("totals:", json.dumps(summary["totals"], ensure_ascii=False))
    print("result:", fg.RESULT_JSON)
    return 2 if (failures or side > 0 or bare_fail) else 0


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ORDER + ["merge"]:
        print(__doc__)
        return 1
    name = sys.argv[1]
    return merge() if name == "merge" else run_one(name)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""T7 最终门禁 + 测试隔离前后对照（qa/gates/final_gate.py）

顺序执行：
  1) tests/run_tests.py
  2) tests/gui_smoke.py
  3) tests/stress_protocol.py
  4) cd app && swift test --disable-sandbox   （注入 PERLER_* 环境变量到临时目录）
  5) cd app && swift build
  6) 残留审计：bare swift test（不注入 env，--skip-bare-swift 可跳过）
     允许新增 output/ 产物与测试 track 键，禁止删除/改写既有 track 用户进度键与根用户 json。

每个步骤前后对仓库用户数据做快照并 diff：
  track/ 全部文件 sha256、根 history.json/queue_state.json/app_settings.json/my_colors.json、
  根目录其它 *.json、output/ 全部文件名+sha256、data/ 全部文件 sha256。

判定：
  - 任一步骤退出码非 0 -> 失败
  - Python 3 套件 / 环境注入的 swift test 出现任何仓库用户数据副作用 -> 失败
  - bare swift test 出现 track/ 删除或改写 / 根 json 删除或改写 -> 失败；
    output/ 仅允许新增与被 prune（记录为「开发态可接受、CI 必须注入 env」）
输出：qa/gates/logs/final/isolation_diff.json + 每步日志。

用法（仓库根）：
  conda run --no-capture-output -n pindou python qa/gates/final_gate.py
  conda run --no-capture-output -n pindou python qa/gates/final_gate.py --skip-bare-swift
  conda run --no-capture-output -n pindou python qa/gates/final_gate.py --snapshot-only
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(ROOT, "qa", "gates", "logs", "final")
RESULT_JSON = os.path.join(LOG_DIR, "isolation_diff.json")

ROOT_FILES = ["history.json", "queue_state.json", "app_settings.json", "my_colors.json"]
TRACKED_DIRS = ["track", "output", "data"]

ENV_VARS = ["PERLER_OUTPUT_DIR", "PERLER_TRACK_DIR", "PERLER_SETTINGS_FILE",
            "PERLER_QUEUE_FILE", "PERLER_HISTORY_FILE", "PERLER_MY_COLORS_FILE"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_meta(path):
    st = os.stat(path)
    return {"sha256": sha256_file(path), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def snapshot_tree(rel_dir):
    base = os.path.join(ROOT, rel_dir)
    if not os.path.isdir(base):
        return {"__dir_missing__": True}
    out = {}
    for cur, dirs, files in os.walk(base):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(cur, name)
            rel = os.path.relpath(full, base)
            try:
                out[rel.replace(os.sep, "/")] = file_meta(full)
            except OSError as exc:
                out[rel.replace(os.sep, "/")] = {"error": str(exc)}
    return out


def snapshot():
    snap = {"root_files": {}, "dirs": {}}
    for name in ROOT_FILES:
        path = os.path.join(ROOT, name)
        snap["root_files"][name] = file_meta(path) if os.path.isfile(path) else {"__missing__": True}
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if os.path.isfile(path) and name.endswith(".json") and name not in ROOT_FILES:
            snap["root_files"]["extra:" + name] = file_meta(path)
    for d in TRACKED_DIRS:
        snap["dirs"][d] = snapshot_tree(d)
    return snap


def _cmp_maps(scope, before, after, diffs):
    for key in sorted(set(before) | set(after)):
        va, vb = before.get(key), after.get(key)
        if va is None:
            diffs.append({"scope": scope, "item": key, "kind": "added"})
        elif vb is None:
            diffs.append({"scope": scope, "item": key, "kind": "removed"})
        elif va.get("sha256") != vb.get("sha256") or va.get("__missing__") != vb.get("__missing__"):
            diffs.append({"scope": scope, "item": key, "kind": "changed",
                          "before": {k: va.get(k) for k in ("sha256", "size")},
                          "after": {k: vb.get(k) for k in ("sha256", "size")}})


def diff_snapshot(before, after):
    diffs = []
    _cmp_maps("root", before["root_files"], after["root_files"], diffs)
    for d in TRACKED_DIRS:
        a, b = before["dirs"][d], after["dirs"][d]
        am, bm = a.get("__dir_missing__", False), b.get("__dir_missing__", False)
        if am or bm:
            if am != bm:
                diffs.append({"scope": d, "item": "<dir>", "kind": "dir_presence",
                              "before_missing": am, "after_missing": bm})
            continue
        _cmp_maps(d, a, b, diffs)
    return diffs


def parse_counts(kind, log_path):
    text = open(log_path, "r", encoding="utf-8", errors="replace").read()
    if kind == "python":
        m = re.findall(r"通过:\s*(\d+)\s+失败:\s*(\d+)", text)
        if m:
            return {"passed": int(m[-1][0]), "failed": int(m[-1][1])}
    else:
        m = re.findall(r"Executed (\d+) tests, with (\d+) failures", text)
        if m:
            return {"passed": int(m[-1][0]), "failed": int(m[-1][1])}
    return {"passed": None, "failed": None}


def make_swift_iso_env():
    iso = tempfile.mkdtemp(prefix="perler_swift_iso_")
    env = dict(os.environ)
    env.update({
        "PERLER_OUTPUT_DIR": os.path.join(iso, "output"),
        "PERLER_TRACK_DIR": os.path.join(iso, "track"),
        "PERLER_SETTINGS_FILE": os.path.join(iso, "app_settings.json"),
        "PERLER_QUEUE_FILE": os.path.join(iso, "queue_state.json"),
        "PERLER_HISTORY_FILE": os.path.join(iso, "history.json"),
        "PERLER_MY_COLORS_FILE": os.path.join(iso, "my_colors.json"),
    })
    return iso, env


def run_step(spec, env_override=None):
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, spec["name"] + ".log")
    before = snapshot()
    started = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    t0 = time.time()
    env = env_override if env_override is not None else dict(os.environ)
    with open(log_path, "wb") as fh:
        proc = subprocess.run(spec["cmd"], cwd=spec["cwd"], stdout=fh,
                              stderr=subprocess.STDOUT, timeout=spec["timeout"], env=env)
    elapsed = round(time.time() - t0, 1)
    ended = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    after = snapshot()
    diffs = diff_snapshot(before, after)
    counts = parse_counts(spec["kind"], log_path)
    return {
        "name": spec["name"],
        "command": " ".join(spec["cmd"]),
        "cwd": spec["cwd"],
        "env_injected": env_override is not None,
        "started": started,
        "ended": ended,
        "elapsed_s": elapsed,
        "exit_code": proc.returncode,
        **counts,
        "log": os.path.relpath(log_path, ROOT),
        "side_effect_count": len(diffs),
        "side_effects": diffs,
    }


def residual_audit(result):
    """bare swift test 的数据安全审计：只允许新增；删除/改写用户 track 键或根 json 视为失败。"""
    removed_or_changed = [
        d for d in result["side_effects"]
        if d["scope"] in ("track", "root") and d["kind"] in ("removed", "changed",
                                                             "dir_presence")
    ]
    output_removed = [d for d in result["side_effects"]
                      if d["scope"] == "output" and d["kind"] == "removed"]
    track_added = [d for d in result["side_effects"]
                   if d["scope"] == "track" and d["kind"] == "added"]
    result["audit"] = {
        "user_data_removed_or_changed": removed_or_changed,
        "track_added_test_keys": [d["item"] for d in track_added],
        "output_removed_by_prune": [d["item"] for d in output_removed],
        "verdict": "FAIL" if removed_or_changed else "PASS",
        "note": "output/ 被 prune 属开发态可接受；CI 必须注入 PERLER_* env 才能零副作用。",
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-only", action="store_true")
    ap.add_argument("--skip-bare-swift", action="store_true")
    ap.add_argument("--skip-swift", action="store_true")
    args = ap.parse_args()

    os.makedirs(LOG_DIR, exist_ok=True)
    if args.snapshot_only:
        snap = snapshot()
        with open(os.path.join(LOG_DIR, "snapshot_only.json"), "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)
        print("snapshot written:", os.path.join(LOG_DIR, "snapshot_only.json"))
        return 0

    app_dir = os.path.join(ROOT, "app")
    steps = [
        {"name": "run_tests", "cwd": ROOT,
         "cmd": [sys.executable, "tests/run_tests.py"], "kind": "python", "timeout": 1800},
        {"name": "gui_smoke", "cwd": ROOT,
         "cmd": [sys.executable, "tests/gui_smoke.py"], "kind": "python", "timeout": 900},
        {"name": "stress_protocol", "cwd": ROOT,
         "cmd": [sys.executable, "tests/stress_protocol.py"], "kind": "python", "timeout": 1800},
    ]
    if not args.skip_swift:
        steps.append({"name": "swift_test_isolated", "cwd": app_dir,
                      "cmd": ["swift", "test", "--disable-sandbox"],
                      "kind": "swift", "timeout": 1800})
        # DSH 沙箱下 SwiftPM 嵌套 sandbox-exec 会被拒，与 swift test 一致加 --disable-sandbox
        steps.append({"name": "swift_build", "cwd": app_dir,
                      "cmd": ["swift", "build", "--disable-sandbox"],
                      "kind": "swift", "timeout": 900})

    iso_dir, swift_env = make_swift_iso_env()
    results = []
    for spec in steps:
        print("\n" + "=" * 72)
        print("[gate]", spec["name"], "->", " ".join(spec["cmd"]))
        env_override = swift_env if spec["name"] == "swift_test_isolated" else None
        result = run_step(spec, env_override)
        results.append(result)
        print("[gate] exit=%s passed=%s failed=%s elapsed=%ss side_effects=%d" % (
            result["exit_code"], result["passed"], result["failed"],
            result["elapsed_s"], result["side_effect_count"]))
        for d in result["side_effects"][:15]:
            print("   side-effect:", json.dumps(d, ensure_ascii=False))

    if not args.skip_swift and not args.skip_bare_swift:
        print("\n" + "=" * 72)
        print("[audit] bare swift test（不注入 env，验证不会删除/改写用户 track 进度键）")
        bare = run_step({"name": "swift_test_bare_audit", "cwd": app_dir,
                         "cmd": ["swift", "test", "--disable-sandbox"],
                         "kind": "swift", "timeout": 1800},
                        env_override=dict(os.environ))
        bare = residual_audit(bare)
        results.append(bare)
        print("[audit] exit=%s passed=%s failed=%s side_effects=%d verdict=%s" % (
            bare["exit_code"], bare["passed"], bare["failed"],
            bare["side_effect_count"], bare["audit"]["verdict"]))
        print("   user_data_removed_or_changed:",
              json.dumps(bare["audit"]["user_data_removed_or_changed"], ensure_ascii=False)[:800])
        print("   track_added_test_keys:", bare["audit"]["track_added_test_keys"])
        print("   output_removed_by_prune(%d):" % len(bare["audit"]["output_removed_by_prune"]),
              bare["audit"]["output_removed_by_prune"][:10])

    main_results = [r for r in results if not r["name"].endswith("_bare_audit")]
    failures = [r for r in main_results if r["exit_code"] != 0]
    main_side_effects = sum(r["side_effect_count"] for r in main_results)
    bare = next((r for r in results if r["name"] == "swift_test_bare_audit"), None)
    bare_fail = bool(bare and bare["audit"]["verdict"] == "FAIL")
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo_root": ROOT,
        "git_head": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "swift_iso_dir": iso_dir,
        "env_vars_injected": ENV_VARS,
        "suites": results,
        "totals": {
            "steps_run": len(main_results),
            "step_failures": len(failures),
            "side_effects_total": main_side_effects,
            "bare_swift_audit_fail": bare_fail,
            "bare_swift_output_pruned": (len(bare["audit"]["output_removed_by_prune"])
                                         if bare else None),
        },
    }
    with open(RESULT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("\n" + "=" * 72)
    print("TOTAL steps=%d failures=%d side_effects=%d bare_swift_audit_fail=%s" % (
        len(main_results), len(failures), main_side_effects, bare_fail))
    print("result:", os.path.relpath(RESULT_JSON, ROOT))
    print("evidence:", os.path.relpath(LOG_DIR, ROOT))
    return 2 if (failures or main_side_effects > 0 or bare_fail) else 0


if __name__ == "__main__":
    sys.exit(main())

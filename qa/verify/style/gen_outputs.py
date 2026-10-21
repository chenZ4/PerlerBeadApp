#!/usr/bin/env python3
"""T17 证据生成：通过真实引擎协议（core_server.py JSON 行）生成
图纸 PNG / 成品预览 / PDF（A4+BOM、1:1）并收集到 qa/verify/evidence/style/<tag>/。
在 conda pindou 环境运行（引擎依赖 numpy/Pillow）。

用法:
  conda run -n pindou python qa/verify/style/gen_outputs.py --tag before|after
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="after")
    ap.add_argument("--source", default=os.path.join(ROOT, "qa/ui/assets/source_eagle.png"))
    ap.add_argument("--out", default=os.path.join(ROOT, "qa/verify/evidence/style"))
    args = ap.parse_args()

    outdir = os.path.join(args.out, args.tag)
    os.makedirs(outdir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="t17_engine_")
    env = dict(os.environ)
    env.update({
        "PERLER_OUTPUT_DIR": os.path.join(tmp, "output"),
        "PERLER_SETTINGS_FILE": os.path.join(tmp, "app_settings.json"),
        "PERLER_QUEUE_FILE": os.path.join(tmp, "queue_state.json"),
        "PERLER_HISTORY_FILE": os.path.join(tmp, "history.json"),
        "PERLER_MY_COLORS_FILE": os.path.join(tmp, "my_colors.json"),
    })
    os.makedirs(env["PERLER_OUTPUT_DIR"], exist_ok=True)

    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "core_server.py")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, cwd=ROOT)
    rid = [0]

    def req(op, params=None):
        rid[0] += 1
        my = rid[0]
        proc.stdin.write(json.dumps({"id": my, "op": op, "params": params or {}}) + "\n")
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                err = proc.stderr.read() if proc.stderr else ""
                raise RuntimeError("engine closed: " + err[-2000:])
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == my and "event" not in msg:
                return msg

    def gen(name, grid, cell, effects=None, palette="mard_221", show_finished=True,
            source=None):
        params = {"image_path": source or args.source, "grid_w": grid, "grid_h": grid,
                  "cell_size": cell, "palette": palette,
                  "show_finished": show_finished}
        if effects:
            params["effects"] = effects
        r = req("generate", params)
        if not r.get("ok"):
            raise RuntimeError(name + " generate failed: " + json.dumps(r, ensure_ascii=False))
        chart = os.path.join(outdir, name + "_chart.png")
        shutil.copyfile(r["chart_path"], chart)
        finished = None
        if r.get("finished_path"):
            finished = os.path.join(outdir, name + "_finished.png")
            shutil.copyfile(r["finished_path"], finished)
        return {"name": name, "grid": grid, "cell": cell,
                "chart_path": chart, "finished_path": finished,
                "chart_size": r.get("chart_size"), "finished_size": r.get("finished_size"),
                "total_beads": r.get("total_beads"),
                "color_count": len(r.get("color_stats") or {}),
                "palette": r.get("palette"),
                "warnings": r.get("warnings"),
                "color_stats": r.get("color_stats"),
                "request": params}

    cases = []
    cases.append(gen("grid29_cell20_light", 29, 20))
    cases.append(gen("grid60_cell60_light", 60, 60))
    cases.append(gen("grid100_cell16_light", 100, 16))
    cases.append(gen("grid60_cell16_light", 60, 16))
    cases.append(gen("grid60_cell60_dark", 60, 60,
                     effects=[{"id": "dark_chart", "params": {}}]))
    # 透明素材 → finished 透明/未覆盖区域应露出 paper 纸底（T17 ②）
    from PIL import Image as _PILImage, ImageDraw as _PILDraw
    trans_src = os.path.join(tmp, "transparent_src.png")
    tim = _PILImage.new("RGBA", (240, 240), (0, 0, 0, 0))
    td = _PILDraw.Draw(tim)
    td.ellipse([60, 40, 180, 200], fill=(200, 60, 60, 255))
    td.rectangle([10, 210, 40, 235], fill=(80, 120, 200, 255))
    tim.save(trans_src)
    cases.append(gen("finished_transparent", 29, 20, source=trans_src))

    # PDF：A4（含 BOM 页）、A4 黑白、1:1 实物
    base = [c for c in cases if c["name"] == "grid60_cell60_light"][0]
    pdfs = {}
    for name, mode, bw in [("pdf_a4_bom", "a4", False),
                           ("pdf_a4_bw", "a4", True),
                           ("pdf_1x1", "1x1", False)]:
        path = os.path.join(outdir, name + ".pdf")
        r = req("export_pdf", {"source_path": base["chart_path"], "save_path": path,
                               "mode": mode, "cell_size": 60,
                               "bom": base["color_stats"], "bw": bw})
        if not r.get("ok"):
            raise RuntimeError(name + " pdf failed: " + json.dumps(r, ensure_ascii=False))
        pdfs[name] = {"path": path, "mode": mode, "bw": bw}

    manifest = {
        "tag": args.tag,
        "source": args.source,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine_root": ROOT,
        "cases": cases,
        "pdfs": pdfs,
    }
    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    proc.stdin.close()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    print("generated", len(cases), "cases +", len(pdfs), "pdfs ->", outdir)
    for c in cases:
        print("  ", c["name"], c["chart_size"], "beads=", c["total_beads"],
              "colors=", c["color_count"], "warnings=", c["warnings"])


if __name__ == "__main__":
    main()

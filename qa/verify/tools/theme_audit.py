#!/usr/bin/env python3
"""T10 主题数值审计：从产品源码解析 T9 色板 tokens，计算 WCAG 对比度与 HSV，
检查是否仍有「饱和红/绿并置」。只读产品源码，不修改产品代码。
输出: qa/verify/evidence/theme_tokens.json + stdout markdown 表格
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DS = ROOT / "app/Sources/PerlerApp/DesignSystem.swift"
OUT = ROOT / "qa/verify/evidence/theme_tokens.json"

def parse_tokens(path: Path):
    s = path.read_text(encoding="utf-8")
    # static let name = Color.dynamic(light: 0x..., dark: 0x...)
    pat = re.compile(
        r"static\s+let\s+(\w+)\s*=\s*Color\.dynamic\(\s*light:\s*0x([0-9A-Fa-f]{6})\s*,\s*dark:\s*0x([0-9A-Fa-f]{6})\s*\)")
    tokens = {}
    for m in pat.finditer(s):
        tokens[m.group(1)] = {"light": "#" + m.group(2).upper(), "dark": "#" + m.group(3).upper()}
    return tokens, s

def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def lum(rgb):
    def ch(v):
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)

def contrast(a, b):
    la, lb = lum(hex2rgb(a)), lum(hex2rgb(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

def hsv(hexs):
    r, g, b = [v / 255 for v in hex2rgb(hexs)]
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    h = 0.0
    if d > 1e-6:
        if mx == r:
            h = 60 * (((g - b) / d) % 6)
        elif mx == g:
            h = 60 * ((b - r) / d + 2)
        else:
            h = 60 * ((r - g) / d + 4)
    s = 0 if mx <= 0 else d / mx
    return round(h, 1), round(s, 3), round(mx, 3)

def is_red(h, s, v):
    return (h >= 340 or h <= 20) and s >= 0.55 and v >= 0.35

def is_green(h, s, v):
    return 80 <= h <= 160 and s >= 0.45 and v >= 0.30

def main():
    tokens, src = parse_tokens(DS)
    if not tokens:
        print("未解析到 tokens", file=sys.stderr)
        return 1
    out = {"tokens": {}, "contrast": [], "forbidden": {}}
    for name, modes in tokens.items():
        for mode, hx in modes.items():
            h, s, v = hsv(hx)
            out["tokens"].setdefault(name, {})[mode] = {
                "hex": hx, "hsv": [h, s, v],
                "red_band": is_red(h, s, v), "green_band": is_green(h, s, v),
            }

    pairs = [
        # (前景, 背景, 用途, 最低要求)
        ("ink", "paper", "正文/标题 on 纸底", 4.5),
        ("inkSoft", "paper", "次要文字 on 纸底", 4.5),
        ("inkMuted", "paper", "弱化文字 on 纸底", 4.5),
        ("inkFaint", "paper", "极弱文字 on 纸底", 3.0),
        ("ink", "paperDeep", "正文 on 面板底", 4.5),
        ("inkMuted", "paperDeep", "弱化文字 on 面板底", 4.5),
        ("inkSoft", "paperMat", "正文 on 亮面板", 4.5),
        ("paper", "accent", "按钮文字 on 干邑强调", 4.5),
        ("paper", "ink", "反白文字 on 墨色按钮", 4.5),
        ("accent", "paper", "强调色文字 on 纸底", 4.5),
        ("accent", "paperDeep", "强调色文字 on 面板底", 4.5),
        ("success", "paper", "success on 纸底(状态点/文字)", 3.0),
        ("warning", "paper", "warning on 纸底", 4.5),
        ("danger", "paper", "danger on 纸底", 4.5),
        ("danger", "paperDeep", "danger on 面板底", 4.5),
        ("hairlineStrong", "paper", "发丝线 on 纸底(装饰,≥3)", 3.0),
    ]
    rows = []
    for fg, bg, use, need in pairs:
        for mode in ("light", "dark"):
            if fg not in tokens or bg not in tokens:
                continue
            c = contrast(tokens[fg][mode], tokens[bg][mode])
            rows.append({
                "fg": fg, "bg": bg, "use": use, "mode": mode,
                "fg_hex": tokens[fg][mode], "bg_hex": tokens[bg][mode],
                "ratio": round(c, 2), "min": need, "pass": c >= need,
            })
    out["contrast"] = rows

    # 饱和红/绿 token 检查（亮暗各自）
    for mode in ("light", "dark"):
        reds = [n for n, m in out["tokens"].items() if m.get(mode, {}).get("red_band")]
        greens = [n for n, m in out["tokens"].items() if m.get(mode, {}).get("green_band")]
        out["forbidden"][mode] = {"saturated_red": reds, "saturated_green": greens,
                                  "red_green_coexist": bool(reds and greens)}
    # 全源码扫描饱和红绿十六进制（含非 token 的一次性颜色）
    hexes = set(re.findall(r"0x([0-9A-Fa-f]{6})", src))
    found = {"red": [], "green": []}
    for hx in sorted(hexes):
        h, s, v = hsv("#" + hx)
        if is_red(h, s, v):
            found["red"].append("#" + hx.upper())
        if is_green(h, s, v):
            found["green"].append("#" + hx.upper())
    out["source_hex_scan"] = found

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("| 前景 | 背景 | 模式 | 实测 | 要求 | 结果 | 用途 |")
    print("|---|---|---|---|---|---|---|")
    fails = 0
    for r in rows:
        mark = "PASS" if r["pass"] else "**FAIL**"
        if not r["pass"]:
            fails += 1
        print(f"| {r['fg']} {r['fg_hex']} | {r['bg']} {r['bg_hex']} | {r['mode']} | {r['ratio']}:1 | {r['min']}:1 | {mark} | {r['use']} |")
    print()
    print("forbidden:", json.dumps(out["forbidden"], ensure_ascii=False))
    print("source_hex_scan:", json.dumps(out["source_hex_scan"], ensure_ascii=False))
    print(f"contrast rows={len(rows)} fails={fails}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

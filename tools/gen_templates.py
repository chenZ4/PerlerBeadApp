# tools/gen_templates.py - 生成内置模板库（社区经典款）
import json
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "templates")


def grid(pixels):
    h = len(pixels)
    w = len(pixels[0])
    flat = []
    for row in pixels:
        for v in row:
            flat.append(v if v is not None else "")
    return w, h, flat


TEMPLATES = [
    {
        "id": "heart",
        "name": "爱心",
        "palette": "mard_221",
        "pixels": [
            [None, "A14", "A14", None, None, None, "A14", "A14", None],
            ["A14", "A14", "A14", "A14", None, "A14", "A14", "A14", "A14"],
            ["A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14"],
            ["A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14"],
            ["A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14"],
            [None, "A14", "A14", "A14", "A14", "A14", "A14", "A14", None],
            [None, None, "A14", "A14", "A14", "A14", "A14", None, None],
            [None, None, None, "A14", "A14", "A14", None, None, None],
            [None, None, None, None, "A14", None, None, None, None],
        ],
    },
    {
        "id": "smile",
        "name": "笑脸",
        "palette": "mard_221",
        "pixels": [
            ["A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3"],
            ["A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3"],
            ["A3", "A3", "H7", "A3", "A3", "A3", "A3", "A3", "H7", "A3", "A3"],
            ["A3", "H7", "H7", "A3", "A3", "A3", "A3", "A3", "H7", "H7", "A3"],
            ["A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3"],
            ["A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3"],
            ["A3", "A3", "A3", "A3", "H7", "H7", "H7", "A3", "A3", "A3", "A3"],
            ["A3", "A3", "H7", "H7", "A3", "A3", "A3", "H7", "H7", "A3", "A3"],
            ["A3", "A3", "H7", "A3", "A3", "A3", "A3", "A3", "H7", "A3", "A3"],
            ["A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3"],
            ["A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3"],
        ],
    },
    {
        "id": "strawberry",
        "name": "草莓",
        "palette": "mard_221",
        "pixels": [
            [None, None, None, "B4", None, None, None],
            [None, None, "A11", "A11", "A11", None, None],
            [None, None, "A14", "F1", "A14", None, None],
            [None, "A14", "F1", "A14", "F1", "A14", None],
            ["A14", "F1", "A14", "A14", "A14", "F1", "A14"],
            ["A14", "A14", "A14", "F1", "A14", "A14", "A14"],
            ["A14", "A14", "A14", "A14", "A14", "A14", "A14"],
            [None, "A14", "A14", "A14", "A14", "A14", None],
            [None, None, "A14", "A14", "A14", None, None],
            [None, None, None, "B4", None, None, None],
        ],
    },
    {
        "id": "rainbow",
        "name": "彩虹",
        "palette": "mard_221",
        "pixels": [
            ["H7", "H7", "H7", "H7", "H7", "H7", "H7", "H7", "H7", "H7", "H7"],
            ["A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14", "A14"],
            ["A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3", "A3"],
            ["B4", "B4", "B4", "B4", "B4", "B4", "B4", "B4", "B4", "B4", "B4"],
            ["C5", "C5", "C5", "C5", "C5", "C5", "C5", "C5", "C5", "C5", "C5"],
            ["D4", "D4", "D4", "D4", "D4", "D4", "D4", "D4", "D4", "D4", "D4"],
            ["E5", "E5", "E5", "E5", "E5", "E5", "E5", "E5", "E5", "E5", "E5"],
            [None, None, None, None, None, None, None, None, None, None, None],
        ],
    },
    {
        "id": "ghost",
        "name": "小幽灵",
        "palette": "mard_221",
        "pixels": [
            [None, "H1", "H1", "H1", "H1", "H1", "H1", None],
            ["H1", "H1", "H1", "H1", "H1", "H1", "H1", "H1"],
            ["H1", "H1", "H7", "H1", "H7", "H1", "H1", "H1"],
            ["H1", "H1", "H1", "H1", "H1", "H1", "H1", "H1"],
            ["H1", "H1", "H1", "H1", "H1", "H1", "H1", "H1"],
            ["H1", "H1", "H1", "H1", "H1", "H1", "H1", "H1"],
            ["H1", "H1", "H1", "H1", "H1", "H1", "H1", "H1"],
            ["H1", "H1", "H1", "H1", "H1", "H1", "H1", "H1"],
            ["H1", "H1", "H1", "H1", "H1", "H1", "H1", "H1"],
        ],
    },
    {
        "id": "four_leaf",
        "name": "四叶草",
        "palette": "mard_221",
        "pixels": [
            [None, None, "B4", "B4", None, None],
            [None, "B4", "B2", "B2", "B4", None],
            ["B4", "B2", "B2", "B2", "B2", "B4"],
            ["B4", "B2", "B2", "B2", "B2", "B4"],
            [None, "B4", "B2", "B2", "B4", None],
            [None, None, "B4", "B4", None, None],
        ],
    },
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for t in TEMPLATES:
        w, h, flat = grid(t["pixels"])
        data = {"id": t["id"], "name": t["name"], "palette": t["palette"],
                "width": w, "height": h, "pixels": flat}
        path = os.path.join(OUT, f"{t['id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print(path, f"{w}x{h}")


if __name__ == "__main__":
    main()

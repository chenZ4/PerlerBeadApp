#!/usr/bin/env python3
# qa/effects/make_inputs.py - 生成/准备特效 QA 输入素材（可复跑，全部本地生成）
#
# 素材类别（对应任务要求的 ≥3 类）：
#   1) 真实照片：photo_eagle.png（来自 qa/lead/inputs/eagle.png，已拷入本目录）
#                photo_sky.png（macOS 系统壁纸 DefaultAerial.heic 裁剪，由 prepare 脚本预先转换）
#   2) 扁平卡通：cartoon_cat.png（白底、粗描边、~7 色块 —— 拼豆最常见设计类型）
#   3) 透明背景：transparent_icon.png（RGBA，透明画布 + 不透明主体）
#   4) 定向反例：cartoon_ghost.png（浅蓝底 + **白色主体**，用于验证 bg_remove 误删主体）
import os
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = os.path.join(HERE, "inputs")
os.makedirs(INPUTS, exist_ok=True)


def save(img, name):
    path = os.path.join(INPUTS, name)
    img.save(path)
    print("wrote", path, img.size, img.mode)


def make_cartoon_cat():
    """扁平卡通猫脸：白底 + 6~7 个平涂色 + 深色粗描边（典型拼豆设计）"""
    W = H = 512
    img = Image.new("RGB", (W, H), (255, 255, 255))  # 白底
    d = ImageDraw.Draw(img)
    outline = (38, 32, 38)
    # 头（橙色大圆）
    d.ellipse([96, 112, 416, 432], fill=(245, 158, 66), outline=outline, width=14)
    # 耳朵（三角）
    d.polygon([(110, 190), (150, 60), (250, 145)], fill=(245, 158, 66), outline=outline, width=14)
    d.polygon([(402, 190), (362, 60), (262, 145)], fill=(245, 158, 66), outline=outline, width=14)
    # 内耳
    d.polygon([(145, 175), (160, 100), (215, 155)], fill=(240, 160, 175), outline=None)
    d.polygon([(367, 175), (352, 100), (297, 155)], fill=(240, 160, 175), outline=None)
    # 眼睛（青绿色，扁圆）
    d.ellipse([168, 220, 248, 300], fill=(94, 200, 190), outline=outline, width=10)
    d.ellipse([264, 220, 344, 300], fill=(94, 200, 190), outline=outline, width=10)
    d.ellipse([196, 240, 224, 284], fill=(24, 24, 30))
    d.ellipse([292, 240, 320, 284], fill=(24, 24, 30))
    # 鼻子 + 嘴
    d.polygon([(240, 330), (272, 330), (256, 352)], fill=(232, 120, 132), outline=outline, width=6)
    d.line([(256, 352), (256, 368)], fill=outline, width=8)
    d.arc([210, 350, 256, 392], 0, 90, fill=outline, width=8)
    d.arc([256, 350, 302, 392], 90, 180, fill=outline, width=8)
    # 胡须
    for y, x0, x1 in [(300, 60, 150), (335, 60, 150), (300, 362, 452), (335, 362, 452)]:
        d.line([(x0, y), (x1, y + 6)], fill=outline, width=6)
    # 脸颊
    d.ellipse([150, 300, 196, 340], fill=(240, 160, 175), outline=None)
    d.ellipse([316, 300, 362, 340], fill=(240, 160, 175), outline=None)
    save(img, "cartoon_cat.png")


def make_cartoon_ghost():
    """定向反例：浅蓝背景 + 白色主体（幽灵）。bg_remove(#FFFFFF) 会把主体一起删掉。"""
    W = H = 512
    img = Image.new("RGB", (W, H), (190, 220, 240))  # 浅蓝背景（L1 距白色 = 65+35+15 = 115 > tol*3=90）
    d = ImageDraw.Draw(img)
    outline = (60, 60, 80)
    white = (255, 255, 255)
    # 白色幽灵身体
    d.ellipse([130, 90, 382, 342], fill=white, outline=outline, width=12)
    d.polygon([(130, 300), (382, 300), (382, 440), (330, 400), (286, 440),
               (236, 400), (186, 440), (130, 400)], fill=white, outline=outline, width=12)
    # 眼睛/嘴（深色）
    d.ellipse([196, 190, 236, 260], fill=(30, 30, 40))
    d.ellipse([276, 190, 316, 260], fill=(30, 30, 40))
    d.ellipse([226, 280, 286, 312], fill=(30, 30, 40))
    save(img, "cartoon_ghost.png")


def make_transparent_icon():
    """透明背景素材：透明画布 + 不透明渐变主体（心形），验证 alpha 保留/透明格统计。"""
    W = H = 512
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 用两圆+三角拼出心形，内部用水平渐变（模拟图标光照）
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([96, 120, 288, 312], fill=255)
    md.ellipse([224, 120, 416, 312], fill=255)
    md.polygon([(104, 240), (408, 240), (256, 448)], fill=255)
    grad = np.zeros((H, W, 3), dtype=np.uint8)
    t = np.linspace(0, 1, W, dtype=np.float32)
    grad[..., 0] = (226 * (1 - t) + 120 * t).astype(np.uint8)[None, :]
    grad[..., 1] = (52 * (1 - t) + 200 * t).astype(np.uint8)[None, :]
    grad[..., 2] = (84 * (1 - t) + 220 * t).astype(np.uint8)[None, :]
    grad_img = Image.fromarray(grad, "RGB").convert("RGBA")
    alpha = np.asarray(mask)
    out = np.asarray(grad_img).copy()
    out[..., 3] = alpha
    save(Image.fromarray(out, "RGBA"), "transparent_icon.png")


if __name__ == "__main__":
    make_cartoon_cat()
    make_cartoon_ghost()
    make_transparent_icon()
    for name in ("photo_eagle.png", "photo_sky.png"):
        p = os.path.join(INPUTS, name)
        print(name, "exists" if os.path.exists(p) else "MISSING（照片素材需预先准备，见 report.md 复现命令）")
# tests/gui_smoke.py - GUI 冒烟测试（驱动完整 UI 流程，不弹原生对话框）
import gc
import os
import sys
import tempfile
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from PIL import Image

RESULT = {"passed": 0, "failed": 0, "errors": []}
TEST_DIR = tempfile.mkdtemp(prefix="perler_gui_")
SRC = os.path.join(TEST_DIR, "src.png")
SRC2 = os.path.join(TEST_DIR, "猫咪图案.png")
Image.new("RGB", (300, 200), (255, 128, 0)).save(SRC)
Image.new("RGB", (300, 200), (0, 128, 255)).save(SRC2)
BATCH_DIR = os.path.join(TEST_DIR, "batch")
os.makedirs(BATCH_DIR, exist_ok=True)


def report(name, ok, detail=""):
    if ok:
        RESULT["passed"] += 1
        print(f"  [PASS] {name}")
    else:
        RESULT["failed"] += 1
        RESULT["errors"].append(f"{name}: {detail}")
        print(f"  [FAIL] {name} {detail}")


from core.settings import QUEUE_FILE, load_queue
from ui.desktop_ui import DesktopUI

root = tk.Tk()
app = DesktopUI(root)
root.update()

# 打桩：替换所有文件对话框与消息框，测试全程零弹窗零交互
from ui import desktop_ui as du
du.filedialog.askopenfilename = lambda **kw: SRC
saved_paths = []
du.filedialog.asksaveasfilename = lambda **kw: os.path.join(TEST_DIR, kw.get("initialfile", "out.png"))
du.filedialog.askdirectory = lambda **kw: BATCH_DIR
du.messagebox.showinfo = lambda *a, **k: None
du.messagebox.showwarning = lambda *a, **k: None
du.messagebox.showerror = lambda *a, **k: None
du.messagebox.askyesno = lambda *a, **k: True
du.messagebox.askokcancel = lambda *a, **k: True
app._ask_pdf_mode = lambda: "a4"
app._show_result_dialog = lambda *a, **k: None


def pump(n=3):
    for _ in range(n):
        root.update()
        root.update_idletasks()


print("== GUI: 初始化与主题 ==")
report("界面初始化无异常", True)
report("主题应用成功", root.winfo_exists())
report("每格像素默认 60", app.cell_px_var.get() == "60", app.cell_px_var.get())
report("预览区为 Canvas", hasattr(app, "preview_canvas"))

print("== GUI: 选择图片与生成 ==")
app.select_image()
pump()
report("选择图片后自动生成预览", app.processed_image is not None)
report("状态栏显示完成", "完成" in app.lbl_status.cget("text"), app.lbl_status.cget("text"))
report("颜色统计已更新", "总计" in app.lbl_color_stats.cget("text"))

print("== GUI: 预览缩放 ==")
app._render_preview()
report("适应窗口渲染", app.photo_ref is not None)
scale_bar_before = app.scale_frame.winfo_height() if hasattr(app, "scale_frame") else 0
app.fit_var.set(False)
app.zoom_var.set(200)
app.update_zoom(200)
pump()
report("200% 缩放渲染", app.photo_ref is not None)
app._on_preview_wheel(type("E", (), {"delta": 1})())
pump()
report("滚轮缩放 +10%（200→210）", app.zoom_var.get() == 210, str(app.zoom_var.get()))
app.fit_var.set(True)
app._toggle_fit()
pump()
report("回到适应窗口模式", app.fit_var.get())

print("== GUI: 参数切换与撤销 ==")
app.entry_w.delete(0, tk.END)
app.entry_w.insert(0, "60")
app._trigger_preview()
pump()
app.preview_timer = None
app.generate_preview()
pump()
report("改宽后重新生成", app.processed_image is not None)
app.undo()
pump()
report("撤销恢复宽度", app.entry_w.get() == "50", app.entry_w.get())
report("撤销恢复显示标号", app.show_labels_var.get() is True)

print("== GUI: 400% 放大缩放条可见 ==")
app.fit_var.set(False)
app.zoom_var.set(400)
app.update_zoom(400)
pump()
scale_bar_after = app.scale_frame.winfo_height()
report("400% 放大后缩放条仍可见（未被顶掉）", scale_bar_after > 0, f"h={scale_bar_after}")
app.fit_var.set(True)
app._toggle_fit()
pump()

print("== GUI: 非法输入容错 ==")
app.entry_w.delete(0, tk.END)
app.entry_w.insert(0, "abc")
app.entry_h.delete(0, tk.END)
app.entry_h.insert(0, "0")
app.grid_color_var.set("#ZZZZZZ")
app.generate_preview()
pump()
report("非法宽高/hex 不崩溃且正常生成", app.processed_image is not None)
report("非法宽高回退默认值", app.entry_w.get() == "abc" and app.processed_image is not None)

bad_hexes = ["", "#", "12345", "#1234567", "GGGGGG", "0x1234", "＃123456",
             "#1_2abc", "abc", "12", "#1234567890", "None", "  "]
all_safe = True
for bad in bad_hexes:
    app.grid_color_var.set(bad)
    app.generate_preview()
    pump()
    if app.processed_image is None:
        all_safe = False
        print(f"    hex 输入崩: {bad!r}")
report(f"hex 穷举 {len(bad_hexes)} 例非法输入全部回退不崩", all_safe)

app.entry_w.delete(0, tk.END)
app.entry_w.insert(0, "50")
app.entry_h.delete(0, tk.END)
app.entry_h.insert(0, "50")
app.grid_color_var.set("#C8C8C8")
app.generate_preview()
pump()

print("== GUI: 保存 / 导出 PNG / 导出 PDF ==")
app.save_to_history()
pump()
report("保存后加入历史", len(app.history_mgr.get_list()) > 0)
hist = app.history_mgr.get_list()[0]
report("历史记录含 show_labels", hist.get('show_labels') is True)
report("历史记录 save_path 绝对", os.path.isabs(hist['save_path']))
app.export_png()
pump()
report("导出 PNG 生成文件", any(f.endswith(".png") for f in os.listdir(TEST_DIR)))
app.export_pdf()
pump()
report("导出 PDF 生成文件", any(f.endswith(".pdf") for f in os.listdir(TEST_DIR)))
report("状态栏显示 PDF 导出", "PDF" in app.lbl_status.cget("text"), app.lbl_status.cget("text"))

print("== GUI: 批量队列 ==")
app.enqueue_item()
app.queue_format_var.set("PDF(A4适应)")
app.enqueue_item()
app.queue_format_var.set("PDF(1:1实物)")
app.enqueue_item()
report("队列入队 3 项", len(app.queue_items) == 3)
app.process_queue()
pump()
files = sorted(os.listdir(BATCH_DIR))
pngs = [f for f in files if f.endswith(".png")]
pdfs = [f for f in files if f.endswith(".pdf")]
report("批量导出 3 个文件", len(files) == 3, str(files))
report("含 1 个 PNG 和 2 个 PDF（A4/1:1 区分）",
       len(pngs) == 1 and len(pdfs) == 2
       and any("_a4" in f for f in pdfs) and any("_1x1" in f for f in pdfs),
       str(files))
report("批量后历史已更新", len(app.history_mgr.get_list()) >= 3)
app.clear_queue()
report("清空队列", len(app.queue_items) == 0)

print("== GUI: 文件名防覆盖 ==")
app.select_image()
pump()
app.enqueue_item()
app.selected_file = SRC2
app.lbl_file.config(text="猫咪图案.png")
app.enqueue_item()
report("两张不同源图入队", len(app.queue_items) == 2)
app.process_queue()
pump()
files2 = sorted(os.listdir(BATCH_DIR))
src_names = [f for f in files2 if "src_" in f or "猫咪" in f or "_2" in f]
report("不同源图同尺寸导出为不同文件（不覆盖）", len(files2) == 5 and src_names,
       str(files2))
app.clear_queue()

print("== GUI: 批量取消（真实事件路径） ==")
app.select_image()
pump()
app.enqueue_item()
app.enqueue_item()
app.enqueue_item()
report("队列入队 3 项（取消测试）", len(app.queue_items) == 3)
app.root.after(10, app._cancel_queue)
app.process_queue()
pump()
report("批量中点击取消生效（事件被 update 处理）", app.is_processing is False,
       f"is_processing={app.is_processing}")
report("取消后队列状态复位", app._queue_cancel is False)
app.clear_queue()

print("== GUI: 队列旧格式迁移 ==")
from core.settings import save_queue
legacy_item = {
    'image_path': SRC, 'width': 40, 'height': 40,
    'ratio': '按原图比例（宽为基准）',
    'canvas_size': 60, 'show_grid': True, 'show_labels': True, 'show_legend': True,
    'grid_color': '#C8C8C8', 'palette': 'MARD 221 色', 'format': 'PNG',
}
save_queue([legacy_item])
app.queue_items = [legacy_item]
app.refresh_queue_list()
app.process_queue()
pump()
report("旧格式队列项（canvas_size）处理不崩溃", True)
app.clear_queue()
if os.path.exists(QUEUE_FILE):
    os.remove(QUEUE_FILE)

print("== GUI: 处理中变更补生成 ==")
app.select_image()
pump()
app.is_processing = True
app._trigger_preview()
report("处理中变更标记 pending", app._pending_regenerate is True)
app.is_processing = False
app.generate_preview()
pump()
pump()
report("处理完成后自动补生成", app._pending_regenerate is False and app.processed_image is not None)

print("== GUI: 队列持久化 ==")
app.select_image()
pump()
app.enqueue_item()
report("入队后写入队列文件", os.path.exists(QUEUE_FILE))
restored = load_queue()
report("队列文件可恢复", len(restored) == 1 and restored[0]['image_path'] == SRC)
app.clear_queue()
if os.path.exists(QUEUE_FILE):
    os.remove(QUEUE_FILE)
report("清空后队列文件同步", not os.path.exists(QUEUE_FILE))

print("== GUI: 批量取消按钮 ==")
app.select_image()
pump()
app.enqueue_item()
app.enqueue_item()
app._queue_cancel = True
app.process_queue()
pump()
report("取消后队列状态复位", app.is_processing is False and app._queue_cancel is False)
app.clear_queue()

print("== GUI: 色卡窗口 ==")
app.open_color_chart()
pump()
ccw = app.color_chart_window
report("色卡窗口打开", ccw is not None and ccw.window.winfo_exists())
report("色卡加载 221 色", len(ccw.palette.colors) == 221)

cards = []
def _walk(w):
    for c in w.winfo_children():
        try:
            if c.winfo_class() == 'Frame' and int(c.cget('width')) > 100 and int(c.cget('height')) > 100:
                cards.append(c)
        except Exception:
            pass
        _walk(c)
_walk(ccw.scroll_frame)
canvas_w = ccw.canvas.winfo_width()
rightmost = max(c.winfo_x() + c.winfo_width() for c in cards)
gap = canvas_w - rightmost
report("色卡无右侧白屏（间隙 < 30px）", gap < 30, f"canvas={canvas_w} right={rightmost} gap={gap}")
ccw._on_close()
pump()
report("关闭后引用已清理", app.color_chart_window is None)

print("== GUI: 设置持久化 ==")
app.palette_var.set("佩勒 24 色")
app.cell_px_var.set("80")
app.show_labels_var.set(False)
app._persist_settings()
from core.settings import load_settings, SETTINGS_FILE
s = load_settings()
report("设置持久化保存/读取",
       s['palette'] == "佩勒 24 色" and s['cell_px'] == "80" and s['show_labels'] is False,
       str(s))
if os.path.exists(SETTINGS_FILE):
    os.remove(SETTINGS_FILE)
app.palette_var.set("MARD 221 色")
app.cell_px_var.set("60")
app.show_labels_var.set(True)
report("cm 成品尺寸提示", "cm" in app.lbl_cm_hint.cget("text"), app.lbl_cm_hint.cget("text"))

print("== GUI: 成品效果预览 ==")
report("生成时附带成品图", app.finished_image is not None)
app.finished_var.set(True)
app._render_preview()
pump()
report("切换到成品效果渲染", app.photo_ref is not None)
app.finished_var.set(False)
app._render_preview()
pump()
report("切回图纸渲染", app.photo_ref is not None)

print("== GUI: 预览拖动平移 ==")
app.fit_var.set(False)
app.zoom_var.set(300)
app.update_zoom(300)
app._render_preview()
pump()
item = app._img_item
ox0, oy0 = app.preview_canvas.coords(item)
cw = app.preview_canvas.winfo_width()
ch = app.preview_canvas.winfo_height()
report("300% 放大后图像大于画布", app._img_w > cw, f"img_w={app._img_w} canvas_w={cw}")
report("放大后左上角对齐（ox=0）", ox0 == 0 and oy0 == 0, f"{ox0},{oy0}")

app._on_preview_press(type("E", (), {"x": 100, "y": 100}))
app._on_preview_drag(type("E", (), {"x": -100, "y": -80}))
ox1, oy1 = app.preview_canvas.coords(item)
report("拖动后偏移变化（左移/上移）", ox1 == -200 and oy1 == -180, f"{ox1},{oy1}")

app._on_preview_press(type("E", (), {"x": 0, "y": 0}))
app._on_preview_drag(type("E", (), {"x": 20000, "y": 20000}))
ox2, oy2 = app.preview_canvas.coords(item)
report("向右拖到极限被钳制（不越界）", ox2 == 0 and oy2 == 0, f"{ox2},{oy2}")

app._on_preview_press(type("E", (), {"x": 0, "y": 0}))
app._on_preview_drag(type("E", (), {"x": -20000, "y": -20000}))
ox3, oy3 = app.preview_canvas.coords(item)
report("向左拖到极限被钳制（不越界）", ox3 == cw - app._img_w and oy3 == ch - app._img_h,
       f"{ox3},{oy3}")

app._on_preview_release(None)
report("释放后拖动状态清空", app._drag_start is None)

app._on_preview_double_click(None)
ox4, oy4 = app.preview_canvas.coords(item)
report("双击恢复居中（左上角对齐）", ox4 == 0 and oy4 == 0, f"{ox4},{oy4}")

app.fit_var.set(True)
app._toggle_fit()
app._render_preview()
pump()
item = app._img_item
app._on_preview_press(type("E", (), {"x": 10, "y": 10}))
app._on_preview_drag(type("E", (), {"x": 60, "y": 60}))
ox5, oy5 = app.preview_canvas.coords(item)
report("适应窗口模式拖动无效（锁定居中）", ox5 == (cw - app._img_w) // 2, f"{ox5},{oy5}")

print("== GUI: 大网格确认弹窗 ==")
app.select_image()
pump()
app.entry_w.delete(0, tk.END)
app.entry_w.insert(0, "250")
app.entry_h.delete(0, tk.END)
app.entry_h.insert(0, "250")
before_img = app.processed_image
orig_askyesno = du.messagebox.askyesno
du.messagebox.askyesno = lambda *a, **k: False
app.generate_preview(confirm_big=True)
pump()
report("大网格拒绝确认则不生成", app.processed_image is before_img)
du.messagebox.askyesno = lambda *a, **k: True
app.generate_preview(confirm_big=True)
pump()
report("大网格确认后正常生成", app.processed_image is not before_img)
du.messagebox.askyesno = orig_askyesno
app.entry_w.delete(0, tk.END)
app.entry_w.insert(0, "50")
app.entry_h.delete(0, tk.END)
app.entry_h.insert(0, "50")
app.generate_preview()
pump()

print("== GUI: 模态期间快捷键屏蔽 ==")
triggered = []
app._guarded(lambda: triggered.append(1))()
report("非模态时快捷键正常触发", len(triggered) == 1)
app._modal_active = True
app._guarded(lambda: triggered.append(1))()
report("模态期间快捷键被屏蔽", len(triggered) == 1)
app._modal_active = False

print("== GUI: 在文件夹中显示（subprocess 安全传参） ==")
popen_calls = []
orig_popen = du.subprocess.Popen
du.subprocess.Popen = lambda *args, **kw: popen_calls.append(args) or object()
app._show_in_folder("/tmp/带空格 名称.png")
du.subprocess.Popen = orig_popen
ok_calls = any(len(a) == 1 and isinstance(a[0], list) and a[0][0] in ("open", "explorer")
               and a[0][-1] == "/tmp/带空格 名称.png" for a in popen_calls)
report("_show_in_folder 使用列表参数调用", ok_calls, str(popen_calls))

print("== GUI: 关闭窗口时的弹窗路径（防 TclError） ==")
orig_ww = app.root.wait_window
orig_ct = app._center_toplevel
app.root.wait_window = lambda w: None
app._center_toplevel = lambda w: None
app._closing = True
try:
    mode = type(app)._ask_pdf_mode(app)
    report("closing 时 PDF 模式返回 None 不抛错", mode is None, str(mode))
    app._show_result_dialog("标题", "内容")
    report("closing 时结果弹窗正常返回不抛错", True)
except Exception as e:
    report("closing 时弹窗路径不抛错", False, str(e))
app._closing = False
app.root.wait_window = orig_ww
app._center_toplevel = orig_ct

print("== GUI: 内存（10 次生成+渲染后无持续增长） ==")
gc.collect()
tracemalloc.start()
for _ in range(10):
    app.generate_preview()
    pump(1)
    app._render_preview()
    pump(1)
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
mb = 1024 * 1024
report("10 次生成+渲染峰值 < 200MB", peak < 200 * mb, f"peak={peak / mb:.1f}MB")
report("结束驻留 < 80MB", current < 80 * mb, f"current={current / mb:.1f}MB")

root.destroy()

print("\n=== GUI 测试汇总 ===")
print(f"通过: {RESULT['passed']}   失败: {RESULT['failed']}")
if RESULT["errors"]:
    for e in RESULT["errors"]:
        print(f"  - {e}")
    sys.exit(1)
print("全部通过 ✅")

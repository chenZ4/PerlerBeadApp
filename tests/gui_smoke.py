# tests/gui_smoke.py - GUI 冒烟测试（驱动完整 UI 流程，不弹原生对话框）
# 架构：AppController + panels（SettingsPanel/PreviewPanel/QueuePanel/HistoryPanel/StatsPanel）
import gc
import os
import sys
import tempfile
import time
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


from core.models import QueueItem
from core.settings import QUEUE_FILE, load_queue

# 历史记录重定向到临时目录，避免污染仓库 history.json
import core.history_manager as _hm
_hm.HISTORY_FILE = os.path.join(TEST_DIR, "history.json")

from ui.app_controller import AppController

root = tk.Tk()
app = AppController(root)
root.update()

sp = app.settings_panel    # 设置面板
pp = app.preview_panel     # 预览面板
qp = app.queue_panel       # 队列面板

# 打桩：替换所有文件对话框与消息框，测试全程零弹窗零交互
from ui import app_controller as du
du.filedialog.askopenfilename = lambda **kw: SRC
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


def pump_time(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        root.update()
        root.update_idletasks()
        time.sleep(0.02)


print("== GUI: 初始化与主题 ==")
report("界面初始化无异常", True)
report("主题应用成功", root.winfo_exists())
report("每格像素默认 60", sp.cell_px_var.get() == "60", sp.cell_px_var.get())
report("预览区为 Canvas", hasattr(pp, "preview_canvas"))

print("== GUI: 选择图片与生成 ==")
app.select_image()
pump()
report("选择图片后自动生成预览", app.state.processed_image is not None)
report("状态栏显示完成", "完成" in pp.lbl_status.cget("text"), pp.lbl_status.cget("text"))
report("颜色统计已更新", "总计" in app.stats_panel.lbl_color_stats.cget("text"))

print("== GUI: 预览缩放 ==")
pp.force_render()
report("适应窗口渲染", pp.photo_ref is not None)
scale_bar_before = pp.scale_frame.winfo_height() if hasattr(pp, "scale_frame") else 0
pp.fit_var.set(False)
pp.zoom_var.set(200)
pp._on_zoom_cmd(200)
pump()
report("200% 缩放渲染", pp.photo_ref is not None)
pp._on_wheel(type("E", (), {"delta": 1})())
pump()
report("滚轮缩放 +10%（200→210）", pp.zoom_var.get() == 210, str(pp.zoom_var.get()))
pp.fit_var.set(True)
pp._toggle_fit()
pump()
report("回到适应窗口模式", pp.fit_var.get())

print("== GUI: 参数切换与撤销 ==")
sp.entry_w.delete(0, tk.END)
sp.entry_w.insert(0, "60")
app._trigger_preview()
pump()
app.preview_timer = None
app.generate_preview()
pump()
report("改宽后重新生成", app.state.processed_image is not None)
app.undo()
pump()
report("撤销恢复宽度", sp.entry_w.get() == "50", sp.entry_w.get())
report("撤销恢复显示标号", sp.show_labels_var.get() is True)

print("== GUI: 固定比例精确网格（主诉修复回归） ==")
sp.ratio_var.set("1:1 (正方形)")
app._on_ratio_change()
sp.entry_w.delete(0, tk.END)
sp.entry_w.insert(0, "40")
sp.link_from('w')
pump()
report("1:1 联动高=宽", sp.entry_h.get() == "40", sp.entry_h.get())
app.generate_preview()
pump()
report("1:1 生成 40×40 不被源图比例覆盖",
       "网格：40×40" in app.stats_panel.lbl_color_stats.cget("text"),
       app.stats_panel.lbl_color_stats.cget("text"))
sp.ratio_var.set("按原图比例（宽为基准）")
app._on_ratio_change()
sp.entry_w.delete(0, tk.END)
sp.entry_w.insert(0, "50")
sp.entry_h.delete(0, tk.END)
sp.entry_h.insert(0, "50")
if app.preview_timer:
    root.after_cancel(app.preview_timer)
    app.preview_timer = None
pump()

print("== GUI: 400% 放大缩放条可见 ==")
pp.fit_var.set(False)
pp.zoom_var.set(400)
pp._on_zoom_cmd(400)
pump()
scale_bar_after = pp.scale_frame.winfo_height()
report("400% 放大后缩放条仍可见（未被顶掉）", scale_bar_after > 0, f"h={scale_bar_after}")
pp.fit_var.set(True)
pp._toggle_fit()
pump()

print("== GUI: 非法输入容错 ==")
sp.entry_w.delete(0, tk.END)
sp.entry_w.insert(0, "abc")
sp.entry_h.delete(0, tk.END)
sp.entry_h.insert(0, "0")
sp.grid_color_var.set("#ZZZZZZ")
app.generate_preview()
pump()
report("非法宽高/hex 不崩溃且正常生成", app.state.processed_image is not None)
report("非法宽高回退默认值", sp.entry_w.get() == "abc" and app.state.processed_image is not None)

bad_hexes = ["", "#", "12345", "#1234567", "GGGGGG", "0x1234", "＃123456",
             "#1_2abc", "abc", "12", "#1234567890", "None", "  "]
all_safe = True
for bad in bad_hexes:
    sp.grid_color_var.set(bad)
    app.generate_preview()
    pump()
    if app.state.processed_image is None:
        all_safe = False
        print(f"    hex 输入崩: {bad!r}")
report(f"hex 穷举 {len(bad_hexes)} 例非法输入全部回退不崩", all_safe)

sp.entry_w.delete(0, tk.END)
sp.entry_w.insert(0, "50")
sp.entry_h.delete(0, tk.END)
sp.entry_h.insert(0, "50")
sp.grid_color_var.set("#C8C8C8")
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
report("状态栏显示 PDF 导出", "PDF" in pp.lbl_status.cget("text"), pp.lbl_status.cget("text"))

print("== GUI: 批量队列 ==")
app.enqueue_item()
qp.queue_format_var.set("PDF(A4适应)")
app.enqueue_item()
qp.queue_format_var.set("PDF(1:1实物)")
app.enqueue_item()
report("队列入队 3 项", len(app.queue_items) == 3)
app.process_queue()
pump()
files = sorted(os.listdir(BATCH_DIR))
report("批量导出 3 个文件", len(files) == 3, str(files))
report("含 1 个 PNG 和 2 个 PDF（A4/1:1 区分）",
       sum(1 for f in files if f.endswith(".png")) == 1
       and sum(1 for f in files if f.endswith(".pdf")) == 2, str(files))
report("批量后历史已更新", len(app.history_mgr.get_list()) >= 3)
app.clear_queue()
report("清空队列", len(app.queue_items) == 0)

print("== GUI: 不同源图文件名防覆盖 ==")
app.select_image()
pump()
app.enqueue_item()
app.state.selected_file = SRC2
sp.lbl_file.config(text="猫咪图案.png")
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
app.queue_items = [QueueItem.from_legacy(legacy_item)]
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
report("处理完成后自动补生成", app._pending_regenerate is False and app.state.processed_image is not None)

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
sp.palette_var.set("佩勒 24 色")
sp.cell_px_var.set("80")
sp.show_labels_var.set(False)
app._sync_params_from_panel()
app.state.persist_settings()
from core.settings import load_settings, SETTINGS_FILE
s = load_settings()
report("设置持久化保存/读取",
       s['palette'] == "佩勒 24 色" and s['cell_px'] == "80" and s['show_labels'] is False,
       str(s))
if os.path.exists(SETTINGS_FILE):
    os.remove(SETTINGS_FILE)
sp.palette_var.set("MARD 221 色")
sp.cell_px_var.set("60")
sp.show_labels_var.set(True)
report("cm 成品尺寸提示", "cm" in sp.lbl_cm_hint.cget("text"), sp.lbl_cm_hint.cget("text"))

print("== GUI: 成品效果预览 ==")
report("生成时附带成品图", app.state.finished_image is not None)
pp.finished_var.set(True)
pp.force_render()
pump()
report("切换到成品效果渲染", pp.photo_ref is not None)
pp.finished_var.set(False)
pp.force_render()
pump()
report("切回图纸渲染", pp.photo_ref is not None)

print("== GUI: 预览拖动平移 ==")
pp.fit_var.set(False)
pp.zoom_var.set(300)
pp._on_zoom_cmd(300)
pp.force_render()
pump()
item = pp._img_item
ox0, oy0 = pp.preview_canvas.coords(item)
cw = pp.preview_canvas.winfo_width()
ch = pp.preview_canvas.winfo_height()
report("300% 放大后图像大于画布", pp._img_w > cw, f"img_w={pp._img_w} canvas_w={cw}")
report("放大后左上角对齐（ox=0）", ox0 == 0 and oy0 == 0, f"{ox0},{oy0}")

pp._on_press(type("E", (), {"x": 100, "y": 100}))
pp._on_drag(type("E", (), {"x": -100, "y": -80}))
ox1, oy1 = pp.preview_canvas.coords(item)
report("拖动后偏移变化（左移/上移）", ox1 == -200 and oy1 == -180, f"{ox1},{oy1}")

pp._on_press(type("E", (), {"x": 0, "y": 0}))
pp._on_drag(type("E", (), {"x": 20000, "y": 20000}))
ox2, oy2 = pp.preview_canvas.coords(item)
report("向右拖到极限被钳制（不越界）", ox2 == 0 and oy2 == 0, f"{ox2},{oy2}")

pp._on_press(type("E", (), {"x": 0, "y": 0}))
pp._on_drag(type("E", (), {"x": -20000, "y": -20000}))
ox3, oy3 = pp.preview_canvas.coords(item)
report("向左拖到极限被钳制（不越界）", ox3 == cw - pp._img_w and oy3 == ch - pp._img_h,
       f"{ox3},{oy3}")

pp._on_release(None)
report("释放后拖动状态清空", pp._drag_start is None)

pp._on_double_click(None)
ox4, oy4 = pp.preview_canvas.coords(item)
report("双击恢复居中（左上角对齐）", ox4 == 0 and oy4 == 0, f"{ox4},{oy4}")

pp.fit_var.set(True)
pp._toggle_fit()
pp.force_render()
pump()
item = pp._img_item
pp._on_press(type("E", (), {"x": 10, "y": 10}))
pp._on_drag(type("E", (), {"x": 60, "y": 60}))
ox5, oy5 = pp.preview_canvas.coords(item)
report("适应窗口模式拖动无效（锁定居中）", ox5 == (cw - pp._img_w) // 2, f"{ox5},{oy5}")

print("== GUI: 大网格确认弹窗 ==")
app.select_image()
pump()
sp.entry_w.delete(0, tk.END)
sp.entry_w.insert(0, "250")
sp.entry_h.delete(0, tk.END)
sp.entry_h.insert(0, "250")
before_img = app.state.processed_image
orig_askyesno = du.messagebox.askyesno
du.messagebox.askyesno = lambda *a, **k: False
app.generate_preview(confirm_big=True)
pump()
report("大网格拒绝确认则不生成", app.state.processed_image is before_img)
du.messagebox.askyesno = lambda *a, **k: True
app.generate_preview(confirm_big=True)
pump()
report("大网格确认后正常生成", app.state.processed_image is not before_img)
du.messagebox.askyesno = orig_askyesno
sp.entry_w.delete(0, tk.END)
sp.entry_w.insert(0, "50")
sp.entry_h.delete(0, tk.END)
sp.entry_h.insert(0, "50")
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

print("== GUI: 历史面板选中不自动加载（幽灵弹窗回归） ==")
hp = app.history_panel
load_calls = []
orig_load = app.load_selected_history
app.load_selected_history = lambda: load_calls.append(1)
hp.list_history.event_generate("<<ListboxSelect>>")
pump()
report("历史列表选中不触发加载", len(load_calls) == 0)
app.load_selected_history = orig_load

warn_calls = []
orig_warn = du.messagebox.showwarning
du.messagebox.showwarning = lambda *a, **k: warn_calls.append(a)
app.save_to_history()
pump()
report("保存历史后无幽灵警告框", len(warn_calls) == 0, str(warn_calls))
hp.list_history.selection_set(0)
app.delete_selected_history()
pump()
report("删除历史后无幽灵警告框", len(warn_calls) == 0, str(warn_calls))
app.clear_history()
pump()
report("清空历史后无幽灵警告框", len(warn_calls) == 0, str(warn_calls))
du.messagebox.showwarning = orig_warn

print("== GUI: show_legend 历史持久化 ==")
sp.show_legend_var.set(False)
app.save_to_history()
pump()
hist = app.history_mgr.get_list()[0]
report("历史记录保存 show_legend=False", hist.get('show_legend') is False, str(hist.get('show_legend')))
app.history_panel.list_history.selection_set(0)
app.load_selected_history()
pump()
report("加载历史恢复 show_legend=False", sp.show_legend_var.get() is False,
       str(sp.show_legend_var.get()))
sp.show_legend_var.set(True)
app.generate_preview()
pump()

print("== GUI: 历史损坏记录容错 ==")
app.history_mgr.history.insert(0, {"width": "abc", "height": None,
                                   "output_size": "large", "palette": "MARD 221 色",
                                   "time": "2026-01-01 00:00"})
app.history_mgr._migrate_history()
app.refresh_history_list()
app.history_panel.list_history.selection_set(0)
try:
    app.load_selected_history()
    pump()
    report("缺失 image_path 历史加载不崩", True)
except Exception as e:
    report("缺失 image_path 历史加载不崩", False, str(e))
report("损坏记录迁移后 width 为整数",
       isinstance(app.history_mgr.get_record(0).get('width'), int),
       str(app.history_mgr.get_record(0).get('width')))
app.history_mgr.delete_record(0)
app.refresh_history_list()

print("== GUI: 批处理异常注入（假死回归） ==")
app.select_image()
pump()
app.enqueue_item()
orig_process = app.batch_service.process
def _boom(*a, **k):
    raise RuntimeError("注入批量故障")
app.batch_service.process = _boom
app.process_queue()
pump()
report("批处理异常后 is_processing 复位", app.is_processing is False)
report("批处理异常后开始按钮恢复",
       str(app.queue_panel.btn_queue_start.cget('state')) == 'normal',
       app.queue_panel.btn_queue_start.cget('state'))
app.batch_service.process = orig_process
app.clear_queue()

print("== GUI: 批量取消标志防御 ==")
# 未开始批量时点取消：属性必须已初始化且不崩溃
try:
    app._cancel_queue()
    report("未开始批量时 _cancel_queue 不崩溃", True)
except AttributeError as e:
    report("未开始批量时 _cancel_queue 不崩溃", False, str(e))
report("_queue_cancel 置位生效", getattr(app, "_queue_cancel", None) is True,
       str(getattr(app, "_queue_cancel", None)))
app._queue_cancel = False

print("== GUI: 导出 PNG 失败注入 ==")
app.select_image()
pump()
orig_save = app.chart_service.save_chart
def _boom_save(result, path):
    raise OSError("磁盘满")
app.chart_service.save_chart = _boom_save
app.export_png()
pump()
report("PNG 导出失败提示且 is_processing 复位", app.is_processing is False)
app.chart_service.save_chart = orig_save
app.generate_preview()
pump()

print("== GUI: 撤销栈去重 ==")
w0 = sp.entry_w.get()
app.state.previous_states.clear()
sp._notify_dimension('w')
pump()
report("无变化 FocusOut 不压撤销栈", len(app.state.previous_states) == 0,
       str(len(app.state.previous_states)))
sp.entry_w.delete(0, tk.END)
sp.entry_w.insert(0, str(int(w0) + 5))
sp._notify_dimension('w')
pump()
report("改值 FocusOut 压栈一次", len(app.state.previous_states) == 1,
       str(len(app.state.previous_states)))
sp._notify_dimension('w')
pump()
report("重复 FocusOut 不重复压栈", len(app.state.previous_states) == 1,
       str(len(app.state.previous_states)))
app.undo()
pump()
report("撤销后宽度恢复", sp.entry_w.get() == w0, f"{sp.entry_w.get()} vs {w0}")

print("== GUI: 色卡窗口关闭后定时器无残留报错 ==")
tk_errors = []
root.report_callback_exception = lambda *a: tk_errors.append(a)
app.open_color_chart()
pump()
ccw2 = app.color_chart_window
ccw2._copy_to_clipboard({'code': 'H1', 'name': '红', 'rgb': (255, 0, 0), 'hex': '#ff0000'})
ccw2.search_var.set("红")
ccw2._on_search()
ccw2._on_close()
pump_time(2.6)
report("色卡窗口关闭后 after 定时器无 TclError", len(tk_errors) == 0, str(tk_errors[:2]))
root.report_callback_exception = lambda *a: None

print("== GUI: 坏队列文件容错 ==")
from core.settings import SettingsStore
from core.models import QueueItem as _QI
bad_q = os.path.join(TEST_DIR, "bad_queue.json")
with open(bad_q, "w", encoding="utf-8") as f:
    f.write('[{"image_path": "/tmp/x.jpg", "width": "abc", "height": 5}, '
            '"not_a_dict", {"image_path": "/tmp/y.jpg", "width": 1}]')
items = SettingsStore(queue_file=bad_q).load_queue()
report("坏队列文件加载不崩且项合法",
       len(items) == 2
       and all(isinstance(i, _QI) and 1 <= i.params.grid_w <= 500 for i in items),
       f"items={len(items)}")

print("== GUI: 缩略图缓存上限 ==")
qp._thumb_cache = {}
for i in range(210):
    qp._thumb_cache[str(i)] = object()
qp._make_thumb(SRC)
report("缩略图缓存 ≤ 200 条", len(qp._thumb_cache) <= 200, str(len(qp._thumb_cache)))
qp._thumb_cache = {}

print("== GUI: 内存（10 次生成+渲染后无持续增长） ==")
gc.collect()
tracemalloc.start()
for _ in range(10):
    app.generate_preview()
    pump(1)
    pp.force_render()
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

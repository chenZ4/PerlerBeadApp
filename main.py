# main.py
import sys
import tkinter as tk
from tkinter import messagebox

from core.version import APP_NAME, APP_VERSION

try:
    from tkinterdnd2 import TkinterDnD
    ROOT_CLASS = TkinterDnD.Tk
except ImportError:
    ROOT_CLASS = tk.Tk


def _on_tk_error(exc, val, tb):
    import traceback
    traceback.print_exception(exc, val, tb)
    try:
        root = tk._default_root
        if root is not None:
            root.after(0, lambda: messagebox.showerror("程序错误", f"{exc.__name__}: {val}"))
    except Exception:
        pass


def main():
    if tk.TkVersion < 8.6:
        msg = (f"当前 Tk 版本 {tk.TkVersion} 过旧，无法运行本程序。\n\n"
               "请使用 conda 环境运行：\n"
               "    conda run -n pindou python main.py")
        try:
            r = tk.Tk()
            messagebox.showerror("Tk 版本过低", msg)
            r.destroy()
        except Exception:
            print(msg)
        sys.exit(1)

    root = ROOT_CLASS()
    root.report_callback_exception = _on_tk_error
    try:
        from ui.app_controller import AppController
        AppController(root)
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            messagebox.showerror("启动失败",
                                 f"应用启动失败：\n{e}\n\n请确认已安装依赖并检查运行环境。")
        except Exception:
            pass
        root.destroy()
        sys.exit(1)
    root.mainloop()


if __name__ == "__main__":
    main()

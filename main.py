# main.py
import tkinter as tk
from ui.desktop_ui import DesktopUI

if __name__ == "__main__":
    root = tk.Tk()
    app = DesktopUI(root)
    root.mainloop()
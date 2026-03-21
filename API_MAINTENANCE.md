# PerlerBeadApp 接口维护文档

本文档详细说明了 PerlerBeadApp 项目的核心接口、类和方法，用于开发者维护和扩展功能。

---

## 目录结构

```
PerlerBeadApp/
├── core/                      # 核心业务逻辑层
│   ├── colors.py             # 色卡管理模块
│   ├── processor.py          # 图像处理引擎
│   ├── history_manager.py    # 历史记录管理
│   ├── settings_manager.py   # 设置管理
│   ├── pdf_exporter.py       # PDF 导出模块
│   └── utils.py              # 工具函数
├── ui/                        # 用户界面层
│   ├── win_ui/               # Windows 桌面界面
│   ├── mobile_ui/            # Android 移动界面
│   └── base_ui.py            # 基础 UI 组件
├── services/                  # 服务层
│   └── app_service.py        # 应用服务
└── features/                  # 功能特性模块
    └── base_feature.py       # 基础功能类
```

---

## 核心模块接口

### 1. core/colors.py - 色卡管理模块

#### ColorPalette 类

**功能**：管理拼豆色卡，提供颜色匹配功能

**初始化**：
```python
palette = ColorPalette(palette_name="mard_221")
```

**参数说明**：
- `palette_name` (str): 色卡名称，可选值：
  - `"basic"` - 基础 8 色
  - `"hama_16"` - Hama 16 色
  - `"perler_24"` - Perler 24 色
  - `"mard_221"` - MARD 221 色（默认）

**属性**：
- `colors` (List[Tuple[int, int, int]]): RGB 颜色列表
- `names` (List[str]): 颜色名称列表
- `codes` (List[str]): 色号列表
- `hex_codes` (List[str]): HEX 颜色码列表（动态生成）

**方法**：

```python
def find_closest_color(self, r: int, g: int, b: int) -> Tuple[Tuple[int, int, int], str, str, int]:
    """
    查找最接近的色卡颜色
    
    参数:
        r: 红色通道值 (0-255)
        g: 绿色通道值 (0-255)
        b: 蓝色通道值 (0-255)
    
    返回:
        tuple: (RGB 元组，颜色名称，色号，颜色索引)
    """
```

**使用示例**：
```python
from core.colors import ColorPalette

palette = ColorPalette("mard_221")
closest_rgb, name, code, idx = palette.find_closest_color(120, 80, 200)
print(f"匹配颜色：{name}, 色号：{code}, RGB: {closest_rgb}")
```

---

#### get_palette 函数

```python
def get_palette(palette_name: str = "mard_221") -> ColorPalette:
    """
    获取色卡实例（带缓存机制）
    
    参数:
        palette_name: 色卡名称
    
    返回:
        ColorPalette 实例
    """
```

---

#### PALETTE_OPTIONS 常量

```python
PALETTE_OPTIONS = [
    ("基础 8 色", "basic"),
    ("Hama 16 色", "hama_16"),
    ("Perler 24 色", "perler_24"),
    ("MARD 221 色", "mard_221")
]
```

---

### 2. core/processor.py - 图像处理引擎

#### ImageProcessor 类

**功能**：核心图像处理引擎，负责将图片转换为拼豆图纸

**初始化**：
```python
processor = ImageProcessor()
```

**属性**：
- `output_dir` (str): 输出目录路径，默认 `"output"`
- `pdf_exporter` (PDFExporter): PDF 导出器实例

**方法**：

##### process_image - 单图处理

```python
def process_image(
    image_path: str,
    grid_w: int,
    grid_h: int,
    canvas_size: int = 1500,
    show_grid: bool = True,
    grid_color: Tuple[int, int, int] = (200, 200, 200),
    grid_width: int = 1,
    palette_name: str = "mard_221",
    show_color_legend: bool = True,
    show_row_col_labels: bool = True,
    crop_box: Tuple[int, int, int, int] = None,
    outline_black: bool = False
) -> Tuple[str, Image.Image, dict, int, int, int]:
    """
    生成专业拼豆图纸
    
    参数:
        image_path: 输入图片路径
        grid_w: 网格宽度（豆子数量）
        grid_h: 网格高度（豆子数量）
        canvas_size: 画布大小（像素）
        show_grid: 是否显示网格线
        grid_color: 网格颜色 RGB 元组
        grid_width: 网格线宽度
        palette_name: 色卡名称
        show_color_legend: 是否显示颜色图例
        show_row_col_labels: 是否显示行列标号
        crop_box: 裁剪框 (left, top, right, bottom)
        outline_black: 是否对主体边缘黑化处理
    
    返回:
        tuple: (保存路径，PIL 图像对象，颜色统计字典，总豆子数，网格宽，网格高)
    """
```

**使用示例**：
```python
from core.processor import ImageProcessor

processor = ImageProcessor()
save_path, img, stats, total, w, h = processor.process_image(
    image_path="input.png",
    grid_w=50,
    grid_h=50,
    palette_name="mard_221",
    outline_black=True
)
print(f"图纸已保存至：{save_path}, 共需 {total} 颗豆子")
```

---

##### process_batch - 批量处理

```python
def process_batch(
    image_paths: List[str],
    grid_w: int,
    grid_h: int,
    **kwargs
) -> Generator[dict, None, None]:
    """
    批量处理图像序列（生成器）
    
    参数:
        image_paths: 图片路径列表
        grid_w: 网格宽度
        grid_h: 网格高度
        **kwargs: 其他传递给 process_image 的参数
    
    返回:
        生成器，每次 yield 一个字典：
        {
            "current": 当前处理进度，
            "total": 总数，
            "latest_result": 最新处理结果
        }
    """
```

**使用示例**：
```python
images = ["img1.png", "img2.png", "img3.png"]
for step in processor.process_batch(images, grid_w=50, grid_h=50):
    print(f"处理进度：{step['current']}/{step['total']}")
    if step['latest_result']['status'] == 'success':
        print(f"成功：{step['latest_result']['path']}")
```

---

##### export_to_pdf - 导出 PDF

```python
def export_to_pdf(
    pattern_image: Image.Image,
    color_stats: dict,
    grid_w: int,
    grid_h: int,
    total_beads: int,
    palette_name: str,
    filename: str = None
) -> str:
    """
    导出 PDF 格式图纸
    
    参数:
        pattern_image: PIL 图像对象
        color_stats: 颜色统计字典
        grid_w: 网格宽度
        grid_h: 网格高度
        total_beads: 总豆子数
        palette_name: 色卡名称
        filename: 输出文件名（可选）
    
    返回:
        PDF 保存路径，失败返回 None
    """
```

---

##### export_color_list_pdf - 导出色卡清单

```python
def export_color_list_pdf(
    color_stats: dict,
    total_beads: int,
    palette_name: str,
    filename: str = None
) -> str:
    """
    导出纯色列表 PDF
    
    参数:
        color_stats: 颜色统计字典
        total_beads: 总豆子数
        palette_name: 色卡名称
        filename: 输出文件名（可选）
    
    返回:
        PDF 保存路径，失败返回 None
    """
```

---

### 3. core/history_manager.py - 历史记录管理

#### HistoryManager 类

**功能**：管理用户操作历史记录

**初始化**：
```python
history = HistoryManager()
```

**方法**：

```python
def add_record(
    image_path: str,
    save_path: str,
    width: int,
    height: int,
    ratio_mode: str,
    canvas_size: int,
    show_grid: bool,
    grid_color: str,
    palette_name: str
):
    """添加历史记录"""

def get_list() -> List[dict]:
    """获取所有历史记录"""

def get_record(index: int) -> dict:
    """获取单条记录"""

def clear_history():
    """清空历史记录"""

def delete_record(index: int):
    """删除指定记录"""
```

**使用示例**：
```python
from core.history_manager import HistoryManager

history = HistoryManager()
history.add_record(
    image_path="input.png",
    save_path="output/perler.png",
    width=50,
    height=50,
    ratio_mode="原始比例",
    canvas_size=1500,
    show_grid=True,
    grid_color="#C8C8C8",
    palette_name="MARD 221 色"
)

# 获取所有记录
records = history.get_list()
for record in records:
    print(f"{record['time']} - {record['palette']}")
```

---

### 4. core/settings_manager.py - 设置管理

#### SettingsManager 类

**功能**：管理用户设置和配置文件

**初始化**：
```python
settings = SettingsManager()
```

**方法**：

```python
def get(key: str, default=None) -> any:
    """获取设置值"""

def set(key: str, value: any):
    """设置值并保存"""

def reset_to_default():
    """重置为默认设置"""
```

**默认设置项**：
```python
DEFAULT_SETTINGS = {
    "theme": "light",              # 主题：light/dark
    "default_palette": "mard_221", # 默认色卡
    "default_canvas_size": 1500,   # 默认画布大小
    "default_grid_w": 50,          # 默认网格宽度
    "default_grid_h": 50,          # 默认网格高度
    "show_grid": True,             # 显示网格
    "grid_color": "#C8C8C8",       # 网格颜色
    "show_labels": True,           # 显示标号
    "show_legend": True,           # 显示图例
    "max_history_records": 50,     # 最大历史记录数
    "language": "zh-CN"            # 语言设置
}
```

**使用示例**：
```python
from core.settings_manager import SettingsManager

settings = SettingsManager()

# 读取设置
theme = settings.get("theme")
palette = settings.get("default_palette")

# 修改设置
settings.set("theme", "dark")
settings.set("default_canvas_size", 2000)

# 重置为默认
settings.reset_to_default()
```

---

### 5. core/pdf_exporter.py - PDF 导出模块

#### PDFExporter 类

**功能**：负责生成 PDF 格式的图纸和色卡清单

**初始化**：
```python
exporter = PDFExporter()
```

**方法**：

```python
def export(
    output_path: str,
    pattern_image: Image.Image,
    color_stats: dict,
    grid_w: int,
    grid_h: int,
    total_beads: int,
    palette_name: str
) -> bool:
    """
    导出完整 PDF（包含图纸和色卡清单）
    
    返回:
        bool: 是否成功
    """

def export_color_list_only(
    output_path: str,
    color_stats: dict,
    total_beads: int,
    palette_name: str
) -> bool:
    """
    仅导出色列表
    
    返回:
        bool: 是否成功
    """
```

---

### 6. core/utils.py - 工具函数

```python
def setup_logging() -> logging.Logger:
    """
    配置并返回日志记录器
    
    返回:
        logging.Logger 实例
    """

def get_resource_path(relative_path: str) -> str:
    """
    获取资源文件绝对路径（支持 PyInstaller 打包）
    
    参数:
        relative_path: 相对路径
    
    返回:
        绝对路径
    """
```

---

## UI 层接口

### ui/win_ui/main_window.py - Windows 主窗口

#### DesktopUI 类

**继承**：`QMainWindow`

**功能**：Windows 桌面版主界面

**主要属性**：
- `processor` (ImageProcessor): 图像处理器实例
- `history_mgr` (HistoryManager): 历史记录管理器
- `selected_files` (List[str]): 选中的文件列表
- `current_image` (QImage): 当前显示的图像
- `color_stats` (dict): 颜色统计信息
- `total_beads` (int): 总豆子数

**主要方法**：

```python
def _generate_preview():
    """生成预览（异步）"""

def _run_batch():
    """执行批量处理"""

def _save_image():
    """保存 PNG 图像"""

def _export_pdf():
    """导出 PDF"""

def _open_color_chart():
    """打开色卡预览窗口"""

def _toggle_theme():
    """切换主题"""
```

---

### ui/mobile_ui/main_app.py - Android 移动界面

#### MobileUI 类

**功能**：Android 移动版界面（待完善）

---

## 扩展开发指南

### 1. 添加新色卡

在 `core/colors.py` 中添加：

```python
elif palette_name == "custom_palette":
    self.colors = [(R, G, B), ...]  # RGB 元组列表
    self.names = ["颜色名 1", "颜色名 2", ...]
    self.codes = ["色号 1", "色号 2", ...]
```

然后在 `PALETTE_OPTIONS` 中添加显示名称：

```python
PALETTE_OPTIONS.append(("自定义色卡", "custom_palette"))
```

---

### 2. 添加新的图像处理功能

继承 `ImageProcessor` 类：

```python
from core.processor import ImageProcessor

class CustomProcessor(ImageProcessor):
    def process_image(self, image_path, **kwargs):
        # 调用父类方法
        result = super().process_image(image_path, **kwargs)
        
        # 添加自定义处理逻辑
        # ...
        
        return result
```

---

### 3. 添加新的 UI 主题

在 `main_window.py` 中添加主题样式：

```python
CUSTOM_THEME = """
QMainWindow { background-color: #...; color: #...; }
QPushButton { ... }
// ... 其他样式
"""
```

在 `_apply_theme` 方法中添加切换逻辑。

---

### 4. 添加新的导出格式

创建新的导出器类：

```python
# core/svg_exporter.py
class SVGExporter:
    def export(self, pattern_image, color_stats, **kwargs):
        # SVG 导出逻辑
        pass
```

在 `ImageProcessor` 中添加调用方法。

---

## 常见维护问题

### Q1: 颜色匹配不准确？

**解决**：
1. 检查色卡数据是否正确加载
2. 调整 `find_closest_color` 方法的距离算法
3. 考虑使用不同的颜色空间（如 LAB）

### Q2: 生成的图纸模糊？

**解决**：
1. 增加 `canvas_size` 参数
2. 检查 `cell_size` 计算逻辑
3. 确保保存时使用高质量参数：`image.save(path, quality=100, dpi=(300, 300))`

### Q3: 批量处理内存占用过高？

**解决**：
1. 使用生成器逐张处理
2. 及时释放已处理图像的内存
3. 添加批处理大小限制

---

## 版本历史

### v0.0.1 (当前版本)
- ✅ 基础图像处理功能
- ✅ 多色卡支持
- ✅ 批量处理
- ✅ 局部裁剪
- ✅ 边缘黑化
- ✅ PNG/PDF导出
- ✅ 历史记录管理
- ✅ 设置管理
- ✅ 双主题切换

### 计划功能
- [ ] 自定义色卡导入
- [ ] SVG 格式导出
- [ ] 图纸编辑功能
- [ ] 云端同步
- [ ] 移动端完善

---

## 联系方式

如有问题或建议，请：
1. 提交 Issue
2. 联系项目维护者

---

**最后更新**: 2026-03-19
**维护者**: PerlerBeadApp Team

# 📁 PerlerBeadApp 项目架构说明

## 项目概述
**拼豆图纸生成器** - 将图片转换为拼豆制作图纸的专业工具

---

## 🏗️ 项目架构

```
PerlerBeadApp/
│
├── 📄 核心文件
│   ├── main.py                 # 程序入口（启动界面）
│   ├── config.py               # 全局配置和常量定义
│   ├── requirements.txt        # Python 依赖包列表
│   └── README.md               # 项目使用说明
│
├── 🔧 core/                    # 核心业务逻辑层
│   ├── __init__.py             # 模块导出
│   ├── processor.py            # 图像处理核心（网格转换、颜色映射）
│   ├── colors.py               # 色卡管理（多色卡支持、颜色匹配）
│   ├── pdf_exporter.py         # PDF 文档生成器
│   ├── history_manager.py      # 历史记录管理（保存/加载历史）
│   ├── settings_manager.py     # 用户设置管理（读取/保存配置）
│   └── utils.py                # 工具函数（日志、资源路径）
│
├── 🎨 ui/                      # 用户界面层
│   ├── __init__.py             # UI 模块导出
│   ├── base_ui.py              # UI 基类（通用组件）
│   ├── color_chart_ui.py       # 色卡预览界面
│   ├── win_ui/                 # Windows 桌面版界面
│   │   ├── __init__.py
│   │   └── main_window.py      # 主窗口（DesktopUI）
│   └── mobile_ui/              # 移动版界面（预留）
│
├── 🚀 features/                # 扩展功能模块
│   └── base_feature.py         # 功能特性基类（用于插件式扩展）
│
├── ⚙️ services/                # 服务层（预留，用于未来服务）
│
├── 📦 resources/               # 资源文件目录
│   ├── fonts/                  # 字体文件
│   └── icons/                  # 图标资源
│
├── 📤 output/                  # 输出文件目录
│   └── (生成的 PNG/PDF 图纸保存在此)
│
├── 🎨 assets/                  # 静态资源（占位符）
│
└── 📝 配置文件
    ├── config.json             # 用户设置（自动生成）
    └── history.json            # 历史记录数据（自动生成）
```

---

## 📊 模块职责

### 1. **core/ - 核心业务逻辑**
- **processor.py**: 图像处理（图片缩放、网格映射、颜色计算）
- **colors.py**: 色卡管理（4 种预设色卡、颜色匹配算法）
- **pdf_exporter.py**: PDF 文档生成（图案 + 颜色清单）
- **history_manager.py**: 历史记录 CRUD 操作
- **settings_manager.py**: 用户设置持久化
- **utils.py**: 日志设置、资源路径处理

### 2. **ui/ - 用户界面**
- **base_ui.py**: UI 基类（通用样式和组件）
- **color_chart_ui.py**: 独立的色卡预览窗口
- **win_ui/main_window.py**: Windows 版主界面（包含所有交互功能）
- **mobile_ui/**: 移动端界面（预留）

### 3. **features/ - 扩展功能**
- **base_feature.py**: 功能插件基类（支持后续扩展新功能）

### 4. **resources/ - 资源文件**
- 存放字体、图标等静态资源

---

## 🔄 数据流

```
用户操作 (ui/)
    ↓
事件处理 (main_window.py)
    ↓
业务逻辑 (core/processor.py, core/colors.py)
    ↓
数据处理
    ↓
结果返回 (ui/)
    ↓
显示给用户
```

---

## 🛠️ 技术栈

- **GUI 框架**: PySide6 (Qt for Python)
- **图像处理**: Pillow (PIL)
- **数值计算**: NumPy (优化颜色匹配算法)
- **PDF 生成**: ReportLab
- **开发语言**: Python 3.8+

---

## 📝 清理记录

已清理内容：
- ✅ 删除所有 `__pycache__/` 缓存目录
- ✅ 删除 `.vs/` IDE 临时目录
- ✅ 删除 `perler_app.log` 日志文件
- ✅ 规范化 `requirements.txt` 格式

---

## 🎯 架构优势

1. **分层清晰**: UI、业务逻辑、资源分离
2. **模块化设计**: 每个模块职责明确
3. **可扩展性**: features 支持插件式扩展
4. **跨平台**: 支持 Windows 和 Android（预留）
5. **易维护**: 代码结构清晰，便于协作

---

## 📋 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行程序
python main.py
```

---

**更新日期**: 2026-03-11  
**版本**: v0.0.1

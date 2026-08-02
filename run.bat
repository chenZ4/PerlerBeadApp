@echo off
rem Windows 启动脚本
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo 运行失败，请确认已安装依赖：pip install -r requirements.txt
    pause
)

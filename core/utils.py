# core/utils.py - 通用工具函数
import os
import logging
from pathlib import Path
from datetime import datetime

def setup_logging(log_file="perler_app.log", level=logging.INFO):
    """设置日志系统"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("PerlerApp")

def get_resource_path(relative_path):
    """获取资源文件路径"""
    from config import RESOURCES_DIR
    return RESOURCES_DIR / relative_path

def ensure_directory(path):
    """确保目录存在"""
    Path(path).mkdir(parents=True, exist_ok=True)
    return path

def get_timestamp():
    """获取时间戳字符串"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def validate_image_path(path):
    """验证图片路径"""
    if not path or not os.path.exists(path):
        return False
    valid_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
    return Path(path).suffix.lower() in valid_extensions
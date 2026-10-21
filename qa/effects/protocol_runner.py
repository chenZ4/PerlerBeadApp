#!/usr/bin/env python3
# qa/effects/protocol_runner.py - 以真实 core_server.py 行协议启动引擎，仅把 OUTPUT_DIR 隔离到 qa 临时目录
# 目的：复现 Swift 的真实调用路径，同时避免与并发门禁套件争抢/裁剪共享 output/。
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import core_server  # noqa: E402

if len(sys.argv) > 1:
    tmp = os.path.abspath(sys.argv[1])
    os.makedirs(tmp, exist_ok=True)
    core_server.OUTPUT_DIR = tmp

core_server.serve()

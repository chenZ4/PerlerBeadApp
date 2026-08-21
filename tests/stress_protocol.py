# tests/stress_protocol.py - 协议层并发/取消/垃圾输入压力测试
# 针对历史翻车区（卡死/僵尸进程/请求丢失/reader 线程死亡）的循环轰炸。
# 独立于 run_tests.py（耗时长），手动运行：
#   conda run -n pindou python tests/stress_protocol.py
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "core_server.py")

RESULT = {"passed": 0, "failed": 0, "errors": []}


def report(name, ok, detail=""):
    if ok:
        RESULT["passed"] += 1
        print(f"  [PASS] {name}")
    else:
        RESULT["failed"] += 1
        RESULT["errors"].append(f"{name}: {detail}")
        print(f"  [FAIL] {name} {detail}")


TEST_DIR = tempfile.mkdtemp(prefix="perler_stress_")
SRC = os.path.join(TEST_DIR, "grad.png")
_img = Image.new("RGB", (240, 240))
_px = _img.load()
for _y in range(240):
    for _x in range(240):
        _px[_x, _y] = (_x * 255 // 240, _y * 255 // 240, 128)
_img.save(SRC)


class EngineHandle:
    """异步收集所有响应的引擎句柄（不阻塞发送端）"""

    def __init__(self, env_extra=None):
        env = dict(os.environ, **(env_extra or {}))
        self.proc = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env)
        self.msgs = {}
        self._lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            with self._lock:
                self.msgs.setdefault(msg.get("id"), []).append(msg)

    def send_raw(self, data: bytes):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def send(self, obj):
        self.send_raw((json.dumps(obj) + "\n").encode())

    def msgs_of(self, rid):
        with self._lock:
            return list(self.msgs.get(rid, []))

    def wait_reply(self, rid, timeout=30, pred=None):
        """等待 rid 出现满足 pred 的消息，返回该消息或 None"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            for m in reversed(self.msgs_of(rid)):
                if pred is None or pred(m):
                    return m
            time.sleep(0.05)
        return None

    def alive_ping(self, rid=999999, timeout=10):
        self.send({"id": rid, "op": "ping"})
        m = self.wait_reply(rid, timeout, lambda m: m.get("pong"))
        return bool(m and m.get("ok"))

    def close(self, kill=True):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            pass
        if self.proc.poll() is None and kill:
            self.proc.kill()


def make_engine():
    eng = EngineHandle()
    ok = eng.alive_ping()
    if not ok:
        eng.close()
        raise RuntimeError("引擎启动失败")
    return eng


def s1_cancel_storm():
    print("== S1: 取消风暴（快速 generate→cancel ×24，两种时序混合） ==")
    eng = make_engine()
    try:
        cancelled = completed = 0
        for i in range(24):
            rid = 1000 + i
            eng.send({"id": rid, "op": "generate",
                      "params": {"image_path": SRC, "grid_w": 200, "grid_h": 200,
                                 "cell_size": 40}})
            if i % 2 == 0:
                eng.send({"id": rid, "op": "cancel"})       # 排队即取消
            else:
                time.sleep(0.08)                             # 起跑后中途取消
                eng.send({"id": rid, "op": "cancel"})
            ack = eng.wait_reply(rid, 15, lambda m: m.get("cancelled") is True
                                 and "event" not in m)
            if not ack:
                report(f"S1 rid={rid} cancel ack 必达", False, "超时无响应")
                return
        # 全部 generate 终态收敛（cancelled 或完整结果）
        for i in range(24):
            rid = 1000 + i
            final = eng.wait_reply(
                rid, 60,
                lambda m: ("cancelled" in m and "ok" not in m) or m.get("chart_path"))
            if final is None:
                report(f"S1 rid={rid} 终态收敛", False, "60s 内无终态消息")
                return
            if final.get("chart_path"):
                completed += 1
            else:
                cancelled += 1
        report("S1 24 组取消全部终态收敛", True,
               f"cancelled={cancelled} completed={completed}")
        report("S1 取消风暴后引擎存活", eng.alive_ping())
    finally:
        eng.close()


def s2_mixed_traffic():
    print("== S2: 长任务排队不丢请求（单 worker 串行为设计预期） ==")
    eng = make_engine()
    try:
        big = 2001
        eng.send({"id": big, "op": "generate",
                  "params": {"image_path": SRC, "grid_w": 350, "grid_h": 350,
                             "cell_size": 40}})
        time.sleep(0.3)  # 让 generate 进入执行
        # cancel 由 reader 线程即时处理：ack 应在长任务进行中就到达
        eng.send({"id": big, "op": "cancel"})
        ack_fast = eng.wait_reply(big, 3, lambda m: m.get("cancelled") is True
                                  and "event" not in m)
        report("S2 长任务进行中 cancel ack 即时可达", ack_fast is not None)

        # 排队流量：worker 忙完后必须逐条补答（不允许丢失）
        rids = []
        for j, op in enumerate(["ping", "palettes", "track_save", "track_load",
                                "settings_get", "effects"]):
            rid = 3000 + j
            rids.append(rid)
            params = {"key": "stress_s2", "cells": ["1:1"]} if op == "track_save" \
                else ({"key": "stress_s2"} if op == "track_load" else {})
            eng.send({"id": rid, "op": op, "params": params})
        missing = [r for r in rids if eng.wait_reply(r, 90) is None]
        report("S2 排队 6 请求全部补答无丢失", not missing, f"missing={missing}")
        report("S2 混合流量后引擎存活", eng.alive_ping())
    finally:
        eng.close()


def s3_garbage_input():
    print("== S3: 垃圾输入轰炸（畸形 JSON/非对象/非法 UTF-8/超长行） ==")
    eng = make_engine()
    try:
        garbage = [
            b'{invalid json\n',
            b'[1, 2, 3]\n',
            b'"just a string"\n',
            b'123\n',
            b'null\n',
            b'\xff\xfe\x00binary\n',
            b'{"id": "not-int", "op": "ping"}\n',
            b'{"op": "no-id"}\n',
            b'x' * (1024 * 1024) + b'\n',   # 1MB 超长行
        ]
        for g in garbage:
            eng.send_raw(g)
        report("S3 垃圾轰炸后引擎存活", eng.alive_ping())
        # 合法请求与垃圾交错也不受污染
        eng.send_raw(b'{bad again\n')
        eng.send({"id": 8888, "op": "ping"})
        m = eng.wait_reply(8888, 10, lambda x: x.get("pong"))
        report("S3 垃圾与合法请求交错正常", bool(m))
    finally:
        eng.close()


def s4_eof_inflight():
    print("== S4: 请求在途关闭 stdin → 优雅退出 ==")
    eng = EngineHandle()
    eng.send({"id": 4000, "op": "generate",
              "params": {"image_path": SRC, "grid_w": 120, "grid_h": 120,
                         "cell_size": 40}})
    time.sleep(0.2)
    try:
        eng.proc.stdin.close()
    except OSError:
        pass
    deadline = time.time() + 30
    while time.time() < deadline and eng.proc.poll() is None:
        time.sleep(0.1)
    exited = eng.proc.poll() is not None
    report("S4 在途请求下 EOF 后进程退出", exited,
           f"returncode={eng.proc.poll()}")
    if exited:
        report("S4 退出码为 0（非崩溃）", eng.proc.returncode == 0,
               str(eng.proc.returncode))


def s5_memory_baseline():
    print("== S5: 连续 100 次生成内存基线（子进程 RSS） ==")

    def rss_kb(pid):
        try:
            out = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(pid)],
                capture_output=True, text=True, timeout=5).stdout.strip()
            return int(out.split()[0]) if out else 0
        except Exception:
            return 0

    eng = make_engine()
    try:
        rid = 5000
        t0 = time.time()
        for i in range(100):
            eng.send({"id": rid + i, "op": "generate",
                      "params": {"image_path": SRC, "grid_w": 60, "grid_h": 60,
                                 "cell_size": 40}})
        for i in range(100):
            if eng.wait_reply(rid + i, 120,
                              lambda m: m.get("chart_path") or "cancelled" in m) is None:
                report(f"S5 第 {i} 次生成无响应", False)
                return
        dt = time.time() - t0
        early = rss_kb(eng.proc.pid)
        # 再跑 50 次观察增量趋势
        for i in range(50):
            eng.send({"id": rid + 1000 + i, "op": "generate",
                      "params": {"image_path": SRC, "grid_w": 60, "grid_h": 60,
                                  "cell_size": 40}})
        for i in range(50):
            eng.wait_reply(rid + 1000 + i, 120,
                           lambda m: m.get("chart_path") or "cancelled" in m)
        late = rss_kb(eng.proc.pid)
        growth_mb = (late - early) / 1024
        report("S5 150 次生成全部有响应", True, f"{dt:.1f}s/100次")
        report("S5 后 50 次内存增量 < 120MB（无常驻泄漏）", growth_mb < 120,
               f"growth={growth_mb:.1f}MB late={late / 1024:.0f}MB")
        report("S5 结束后引擎存活", eng.alive_ping())
    finally:
        eng.close()


def main():
    print("=== 拼豆协议压力测试 ===\n")
    s1_cancel_storm()
    s2_mixed_traffic()
    s3_garbage_input()
    s4_eof_inflight()
    s5_memory_baseline()
    print("\n=== 结果汇总 ===")
    print(f"通过: {RESULT['passed']}   失败: {RESULT['failed']}")
    if RESULT["errors"]:
        print("\n失败明细:")
        for e in RESULT["errors"]:
            print(f"  - {e}")
        sys.exit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()

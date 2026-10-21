#!/usr/bin/env python3
"""T3 探针：stress_protocol.py::s5_memory_baseline 的内存断言在当前沙箱下是否退化为恒真？

复刻 tests/stress_protocol.py L237-244 的 rss_kb()，观察 ps 不可用时的行为。
若 ps 调用抛异常 -> rss_kb 返回 0 -> early=late=0 -> growth_mb=0 < 120 -> 断言恒通过。
"""
import subprocess


def rss_kb(pid):
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out.split()[0]) if out else 0
    except Exception as exc:  # noqa: BLE001 - 与 stress_protocol 完全一致
        print(f"  [rss_kb] exception for pid={pid}: {type(exc).__name__}: {exc}")
        return 0


print("== stress_protocol.py::s5_memory_baseline rss_kb 复刻 ==")
early = rss_kb(1)
late = rss_kb(1)
growth_mb = (late - early) / 1024
print(f"early={early} late={late} growth_mb={growth_mb}")
print("S5 断言 'growth_mb < 120' ->", growth_mb < 120,
      "（ps 不可用时 early=late=0，恒真；该断言对内存泄漏零区分力）")

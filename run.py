# -*- coding: utf-8 -*-
"""一条命令跑完全套：

    python run.py                  # 模拟器（无需硬件）
    python run.py --port COM3      # 真板子（需要 pyserial）
    python run.py -k fault         # 只跑故障注入那组

跑完在 output/report.html 出报告。
"""
import argparse
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="真实串口，如 COM3；不给则用模拟器")
    ap.add_argument("--baud", default="115200")
    ap.add_argument("-k", default=None, help="pytest -k 过滤")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()

    if a.port:
        os.environ["DUT_PORT"] = a.port
        os.environ["DUT_BAUD"] = a.baud
        print(f"[DUT] 真机模式：{a.port} @ {a.baud}")
    else:
        print("[DUT] 模拟器模式（无需硬件，故障注入可用）")

    args = ["tests", "-p", "no:cacheprovider", "-q" if not a.v else "-v", "--tb=short"]
    if a.k:
        args += ["-k", a.k]

    code = pytest.main(args)

    sp = os.path.join(HERE, "output", "summary.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            s = json.load(f)
        link = s["link"]
        print("\n" + "=" * 56)
        print(f"  用例 {s['total']}　通过 {s['passed']}　失败 {s['failed']}　跳过 {s['skipped']}")
        print(f"  协议分支覆盖 {s['branch_hit']}/{s['branch_total']}")
        print(f"  命令 {link['sent']} 条　重试 {link['retries']}　超时 {link['timeouts']}")
        print(f"  时延 P50 {link['p50_ms']}ms　P95 {link['p95_ms']}ms　max {link['max_ms']}ms")
        print(f"  报告：{os.path.join(HERE, 'output', 'report.html')}")
        print("=" * 56)
    return code


if __name__ == "__main__":
    sys.exit(main())

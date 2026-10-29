# -*- coding: utf-8 -*-
"""长稳与性能：跑得久不出错，比跑得快更难。

说明：这里的时延是模拟器 + 本机串口抽象层的开销，不代表真机指标；
接真板子跑同一套用例时，这些数字才有物理意义。
"""

ROUNDS = 200
SEQ = [
    ("AT", None), ("TEMP", None), ("HUMI", None),
    ("LED", 1), ("LED", 0), ("RATE", 200), ("STATUS", None),
]


def test_200轮混合命令零失败(make_client):
    c = make_client()
    failures = []
    for i in range(ROUNDS):
        cmd, arg = SEQ[i % len(SEQ)]
        try:
            r = c.send(cmd, arg)
            if r.kind != "ok":
                failures.append((i, cmd, arg, r.raw))
        except TimeoutError as e:
            failures.append((i, cmd, arg, str(e)))
    assert not failures, f"{len(failures)} 条失败，前 3 条: {failures[:3]}"


def test_长稳过程时延不劣化(make_client):
    """前 50 轮与后 50 轮的 P95 不应显著变大——排除缓冲/句柄泄漏。"""
    c = make_client()
    lat = []
    for i in range(ROUNDS):
        cmd, arg = SEQ[i % len(SEQ)]
        lat.append(c.send(cmd, arg).latency)

    def p95(xs):
        xs = sorted(xs)
        return xs[int(0.95 * (len(xs) - 1))]

    head, tail = p95(lat[:50]), p95(lat[-50:])
    assert tail < head * 2 + 0.005, f"时延劣化：前段 {head*1000:.1f}ms → 后段 {tail*1000:.1f}ms"


def test_复位后计数与状态都归零(make_client):
    c = make_client()
    for _ in range(20):
        c.expect_ok("TEMP")
    c.expect_ok("LED", 1)
    c.expect_ok("RESET")
    kv = dict(x.split("=", 1) for x in c.expect_ok("STATUS").value.split(","))
    assert kv["led"] == "0" and int(kv["uptime"]) < 5

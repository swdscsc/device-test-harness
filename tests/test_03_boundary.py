# -*- coding: utf-8 -*-
"""边界值：每个有区间的参数，测「最小值 / 最小值-1 / 最大值 / 最大值+1」。

边界值从协议层读，不在用例里写死——改协议只需要改一处，用例自动跟着变。
"""
import pytest

from protocol import RATE_MAX, RATE_MIN


@pytest.mark.parametrize("value", [RATE_MIN, RATE_MIN + 1, 500, RATE_MAX - 1, RATE_MAX])
def test_速率合法区间内全部接受(client, value):
    client.expect_ok("RATE", value)
    kv = dict(x.split("=", 1) for x in client.expect_ok("STATUS").value.split(","))
    assert kv["rate"] == str(value)


@pytest.mark.parametrize("value", [RATE_MIN - 1, RATE_MAX + 1, 0, -1, 99999])
def test_速率越界全部拒绝(client, value):
    client.expect_err("RATE", value, code=3)


@pytest.mark.parametrize("value,expect", [(0, "ok"), (1, "ok"), (2, "err"), (-1, "err"), (255, "err")])
def test_LED取值边界(client, value, expect):
    if expect == "ok":
        client.expect_ok("LED", value)
    else:
        client.expect_err("LED", value, code=3)


def test_越界操作不改变原有状态(client):
    """关键回归点：被拒绝的写入绝不能"改一半"。"""
    client.expect_ok("RATE", 300)
    client.send("RATE", 5)          # 越界，应被拒
    kv = dict(x.split("=", 1) for x in client.expect_ok("STATUS").value.split(","))
    assert kv["rate"] == "300", f"越界写入污染了状态: {kv}"


def test_超长参数被拒绝(client):
    client.expect_err("RATE", "9" * 200, code=3)


def test_空命令返回未知命令(client):
    r = client.send("")
    assert r.kind == "err", f"空命令应有明确错误码，实际 {r.raw!r}"


def test_命令字大小写混写按未知命令处理(client):
    r = client.send("Led", 1)
    assert r.kind == "err" and r.err_code == 1, f"大小写不符应返回 ERR1，实际 {r.raw!r}"

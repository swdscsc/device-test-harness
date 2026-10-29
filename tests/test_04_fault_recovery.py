# -*- coding: utf-8 -*-
"""故障注入与恢复：这套用例是这个项目存在的理由。

真实产线上的串口不是干净的——丢包、半截帧、串扰乱码、应答错位、设备忙、响应慢，
每一类都要能在不重启设备的前提下恢复。这里逐类注入并验证。
"""
import pytest

# 会让客户端拿不到有效应答的故障（预期超时）
HARD_FAULTS = ["drop", "slow", "truncate"]
# 能被重试机制吸收的故障（预期第 2 次尝试成功）
SOFT_FAULTS = ["garbage", "wrong"]


@pytest.mark.parametrize("fault", HARD_FAULTS)
def test_硬故障后链路可恢复(make_client, fault):
    """丢包 / 慢响应 / 半截帧之后，设备必须还能被重新叫醒。"""
    c = make_client(faults=[fault], retries=0)
    with pytest.raises(TimeoutError):
        c.send("AT")
    attempts = c.recover(max_attempts=3)
    assert attempts is not None, f"{fault} 之后设备失联"


@pytest.mark.parametrize("fault", SOFT_FAULTS)
def test_软故障被重试机制吸收(make_client, fault):
    """乱码 / 应答错位应当由重试吸收，业务层感知不到。"""
    c = make_client(faults=[fault], retries=2)
    r = c.send("AT")
    assert r.kind == "ok" and r.value == "READY"
    assert r.attempts == 2, f"应当在第 2 次尝试成功，实际第 {r.attempts} 次"


def test_忙应答是合法错误而不是超时(make_client):
    """设备回 -ERR:5 说明它还活着——这跟超时有本质区别，测试必须能分辨。"""
    c = make_client(faults=["busy"])
    r = c.send("AT")
    assert r.kind == "err" and r.err_code == 5
    assert c.recover() is not None


def test_应答错位不会被误判为成功(make_client):
    """链路串包时，客户端如果只看"收到东西"就通过，会把 bug 放过。
    这里断言 tag 校验生效：错位应答必须被判为无效。"""
    c = make_client(faults=["wrong"], retries=0)
    with pytest.raises(TimeoutError):
        c.send("AT")


def test_连续三次故障后仍能恢复(make_client):
    c = make_client(faults=["drop", "truncate", "drop"], retries=0)
    for _ in range(3):
        with pytest.raises(TimeoutError):
            c.send("AT")
    assert c.recover(max_attempts=5) is not None


def test_故障后状态未被破坏(make_client):
    """故障只影响链路，不能影响设备状态——恢复后读回的值必须是故障前的值。"""
    c = make_client(faults=[None, "drop", "garbage"], retries=0)
    c.expect_ok("RATE", 250)
    with pytest.raises(TimeoutError):
        c.send("RATE", 300)          # 这次写入被故障吞掉
    c.recover()
    kv = dict(x.split("=", 1) for x in c.expect_ok("STATUS").value.split(","))
    # 丢包意味着那条命令根本没到达固件，所以状态应停在 250 —— 而不是"改了一半"
    assert kv["rate"] == "250", f"故障期间的写入不该生效，实际 {kv}"

# -*- coding: utf-8 -*-
"""协议一致性：每条命令的应答格式、字段含义、状态是否真的被改变。"""


def test_握手返回就绪(client):
    r = client.expect_ok("AT")
    assert r.value == "READY"


def test_版本号符合语义化格式(client):
    r = client.expect_ok("VER")
    parts = r.value.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), f"版本号格式异常: {r.value}"


def test_设备号非空(client):
    r = client.expect_ok("ID")
    assert r.value and r.value.startswith("DT-")


def test_温度是合理范围内的浮点(client):
    r = client.expect_ok("TEMP")
    v = float(r.value)
    assert -40.0 <= v <= 85.0, f"温度越界: {v}"


def test_湿度是合理范围内的浮点(client):
    r = client.expect_ok("HUMI")
    v = float(r.value)
    assert 0.0 <= v <= 100.0, f"湿度越界: {v}"


def test_STATUS字段齐全(client):
    r = client.expect_ok("STATUS")
    kv = dict(x.split("=", 1) for x in r.value.split(","))
    assert set(kv) == {"led", "rate", "uptime"}, f"STATUS 字段不符: {r.value}"
    assert kv["led"].isdigit() and kv["rate"].isdigit() and kv["uptime"].isdigit()


def test_开灯后状态真的变了(client):
    client.expect_ok("LED", 1)
    kv = dict(x.split("=", 1) for x in client.expect_ok("STATUS").value.split(","))
    assert kv["led"] == "1"


def test_关灯后状态真的变了(client):
    client.expect_ok("LED", 1)
    client.expect_ok("LED", 0)
    kv = dict(x.split("=", 1) for x in client.expect_ok("STATUS").value.split(","))
    assert kv["led"] == "0"


def test_设置上报速率后回读一致(client):
    client.expect_ok("RATE", 200)
    kv = dict(x.split("=", 1) for x in client.expect_ok("STATUS").value.split(","))
    assert kv["rate"] == "200"


def test_RESET恢复出厂值(client):
    client.expect_ok("LED", 1)
    client.expect_ok("RATE", 500)
    client.expect_ok("RESET")
    kv = dict(x.split("=", 1) for x in client.expect_ok("STATUS").value.split(","))
    assert kv["led"] == "0" and kv["rate"] == "100", f"复位后状态未恢复: {kv}"


def test_每条应答都以CRLF结尾(client):
    for cmd in ("AT", "VER", "ID", "TEMP", "HUMI", "STATUS"):
        r = client.expect_ok(cmd)
        assert r.raw.endswith("\r\n"), f"{cmd} 应答缺少 CRLF: {r.raw!r}"


def test_连续读数稳定不漂移(client):
    vals = [float(client.expect_ok("TEMP").value) for _ in range(10)]
    assert max(vals) - min(vals) < 2.0, f"温度读数抖动过大: {vals}"

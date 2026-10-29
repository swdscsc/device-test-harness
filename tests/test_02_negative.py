# -*- coding: utf-8 -*-
"""负向用例：设备面对错误输入时，必须给出**明确的错误码**，而不是沉默或崩溃。

这一组是「测试思维」的体现——正向用例谁都会写，边界与异常才见功夫。
"""


def test_未知命令返回ERR1(client):
    client.expect_err("FOO", code=1)


def test_未知命令带参数也返回ERR1(client):
    client.expect_err("FOOBAR", 1, code=1)


def test_参数非数字返回ERR2(client):
    client.expect_err("LED", "abc", code=2)


def test_速率非数字返回ERR2(client):
    client.expect_err("RATE", "fast", code=2)


def test_参数为空返回ERR2(client):
    client.expect_err("RATE", "", code=2)


def test_参数为浮点返回ERR2(client):
    client.expect_err("LED", "1.5", code=2)


def test_非法LED值返回ERR3(client):
    client.expect_err("LED", 2, code=3)


def test_负LED值返回ERR3(client):
    client.expect_err("LED", -1, code=3)


def test_非AT开头返回ERR4(client):
    r = client.send_raw("HELLO\r\n")
    assert r.kind == "err" and r.err_code == 4, f"非 AT 帧应返回 ERR4，实际 {r.raw!r}"


def test_小写命令按协议返回ERR4(client):
    """协议规定命令字大写；小写必须被明确拒绝，而不是"碰巧能用"。
    这条用例锁住协议约定——如果哪天固件改成大小写不敏感，这条会先失败，提醒同步文档。"""
    r = client.send_raw("at+ver\r\n")
    assert r.kind == "err" and r.err_code == 4


def test_错误应答同样以CRLF结尾(client):
    r = client.send("FOO")
    assert r.raw.endswith("\r\n")


def test_报错后设备仍然可用(client):
    """错误处理不能把设备带进死状态——这是最容易被忽略的回归点。"""
    for _ in range(5):
        client.send("FOO")
    assert client.expect_ok("AT").value == "READY"

# -*- coding: utf-8 -*-
"""设备串口命令协议：帧格式、命令表、错误码。

协议刻意做成 AT 指令风格，贴近 ESP8266 / 模组类设备的真实交互方式：
    请求：AT[+CMD[=ARG]]\\r\\n
    成功：+CMD:PAYLOAD\\r\\n
    失败：-ERR:<code>\\r\\n
"""

CRLF = "\r\n"

# 错误码 —— 每一类都对应一个必须被覆盖的测试分支
ERR = {
    1: "UNKNOWN_CMD",
    2: "BAD_PARAM",
    3: "OUT_OF_RANGE",
    4: "MALFORMED",
    5: "BUSY",
}

# 参数合法区间（边界测试的依据，不写在测试里，写在协议层，避免两处不一致）
RATE_MIN, RATE_MAX = 10, 1000
LED_VALUES = (0, 1)


class FrameError(ValueError):
    """帧本身不合法（缺 CRLF、非 AT 开头、超长）。"""


def build(cmd, arg=None):
    """构造请求帧。

    注意 AT 握手是裸帧 `AT`，不是 `AT+AT`——这类"例外"正是测试要盯住的地方。
    """
    if cmd == "AT" and arg is None:
        return f"AT{CRLF}"
    if arg is None:
        return f"AT+{cmd}{CRLF}"
    return f"AT+{cmd}={arg}{CRLF}"


def build_raw(text):
    """原样发送，用于构造畸形帧。"""
    return text


def parse(line):
    """解析响应行，返回 (kind, tag, value)。

    kind: "ok" | "err" | "unknown"
    """
    if line is None:
        raise FrameError("no response")
    s = line.strip()
    if not s:
        raise FrameError("empty line")
    if s.startswith("-ERR:"):
        try:
            return ("err", "ERR", int(s.split(":", 1)[1]))
        except ValueError:
            raise FrameError(f"bad error frame: {s!r}")
    if s.startswith("+"):
        body = s[1:]
        if ":" in body:
            tag, val = body.split(":", 1)
            return ("ok", tag, val)
        return ("ok", body, "")
    raise FrameError(f"unrecognized frame: {s!r}")


# 每条命令成功时应答的 tag —— 客户端用它做「应答错位」校验
EXPECTED_TAG = {
    "AT": "OK",
    "VER": "VER",
    "ID": "ID",
    "TEMP": "TEMP",
    "HUMI": "HUMI",
    "STATUS": "STATUS",
    "LED": "OK",
    "RATE": "OK",
    "RESET": "OK",
}

# 分支清单：协议一共定义了这么多条「命令 × 结局」路径，覆盖率按它算分母
BRANCHES = set()
for _c in ("AT", "VER", "ID", "TEMP", "HUMI", "STATUS", "LED", "RATE", "RESET"):
    BRANCHES.add((_c, "ok"))
for _e in ERR:
    BRANCHES.add(("*", f"err{_e}"))
BRANCHES.add(("*", "timeout"))

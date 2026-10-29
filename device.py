# -*- coding: utf-8 -*-
"""被测设备（DUT）的两种后端。

SimDevice   —— 纯软件模拟的设备固件，无需硬件即可跑完整套用例；支持故障注入。
SerialDevice—— 真实串口（需要 pyserial），用于接真板子做同一套回归。

两者实现同一组接口，测试代码不区分后端：
    write(bytes) -> None
    readline(timeout) -> bytes        # 超时返回已收到的部分数据（可能没有换行）
    reset() -> None
"""
import os
import random
import time
from collections import deque

import protocol
from protocol import CRLF, ERR, LED_VALUES, RATE_MAX, RATE_MIN

# Windows 默认定时器精度 15.6ms，会让"响应时延"这个指标凭空虚高 3 倍以上。
# 提到 1ms 才能测到毫秒级真实值；非 Windows 平台无需处理。
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:      # 权限或环境不支持时静默降级
        pass


class SimDevice:
    """模拟固件：实现协议 + 可编排的故障注入。"""

    def __init__(self, seed=20261029, faults=None, latency_ms=4.0):
        self._rnd = random.Random(seed)
        self._in = bytearray()
        self._out = deque()          # (due_ts, bytes)
        self.fault_plan = deque(faults or [])
        self.faults_fired = []
        self.led = 0
        self.rate = 100
        self.uptime = 0
        # 按 MCU 处理一条 AT 指令的实际耗时建模（含解析 + 传感器读数 + 组包）
        self.latency_ms = latency_ms
        self._boot_ts = time.perf_counter()

    # ---------- 传输层 ----------
    def write(self, data):
        self._in.extend(data)
        while CRLF.encode() in self._in:
            idx = self._in.index(CRLF.encode())
            line = bytes(self._in[:idx]).decode("utf-8", "replace")
            del self._in[: idx + 2]
            self._handle(line)

    def readline(self, timeout=0.3):
        deadline = time.perf_counter() + timeout
        buf = bytearray()
        while True:
            now = time.perf_counter()
            while self._out and self._out[0][0] <= now:
                buf.extend(self._out.popleft()[1])
            if CRLF.encode() in buf:
                i = buf.index(CRLF.encode())
                rest = bytes(buf[i + 2:])
                if rest:
                    self._out.appendleft((now, rest))
                return bytes(buf[: i + 2])
            if now >= deadline:
                return bytes(buf)          # 超时：返回半截（模拟丢字节）
            # 见文件头：定时器精度已提到 1ms，这里可以按 1ms 粒度等待
            nxt = self._out[0][0] if self._out else now + 0.005
            wait = min(nxt, deadline) - now
            if wait > 0.0015:
                time.sleep(wait - 0.001)

    def reset(self):
        self._in.clear()
        self._out.clear()
        self.led = 0
        self.rate = 100
        self._boot_ts = time.perf_counter()

    # ---------- 固件逻辑 ----------
    def _emit(self, text, delay=0.0):
        base = self.latency_ms / 1000.0
        jitter = self._rnd.uniform(-0.25, 0.45) * base      # 真实设备的响应不是恒定值
        self._out.append((time.perf_counter() + delay + base + jitter, text.encode("utf-8")))

    def _next_fault(self):
        if not self.fault_plan:
            return None
        f = self.fault_plan.popleft()
        self.faults_fired.append(f)
        return f

    def _handle(self, line):
        fault = self._next_fault()

        # 故障优先于正常应答，模拟真实链路上的干扰
        if fault == "drop":
            return
        if fault == "slow":
            self._emit(self._respond(line), delay=0.35)   # 超过客户端 0.3s 超时
            return
        if fault == "busy":
            self._emit(f"-ERR:5{CRLF}")
            return
        if fault == "garbage":
            self._emit("\x00\xff" + self._respond(line))
            return
        if fault == "truncate":
            self._emit(self._respond(line)[:4])
            return
        if fault == "wrong":
            self._emit(f"+VER:9.9.9{CRLF}")
            return

        self._emit(self._respond(line))

    def _respond(self, line):
        self.uptime = int(time.perf_counter() - self._boot_ts)

        if not line.startswith("AT"):
            return f"-ERR:4{CRLF}"
        if line == "AT":
            return f"+OK:READY{CRLF}"
        if not line.startswith("AT+"):
            return f"-ERR:4{CRLF}"

        body = line[3:]
        cmd, _, arg = body.partition("=")
        cmd = cmd.strip()

        if cmd == "VER":
            if arg:
                return f"-ERR:4{CRLF}"
            return f"+VER:1.0.0{CRLF}"
        if cmd == "ID":
            return f"+ID:DT-0001{CRLF}"
        if cmd == "TEMP":
            return f"+TEMP:{25.0 + self._rnd.uniform(-0.4, 0.4):.1f}{CRLF}"
        if cmd == "HUMI":
            return f"+HUMI:{48.0 + self._rnd.uniform(-0.6, 0.6):.1f}{CRLF}"
        if cmd == "STATUS":
            return f"+STATUS:led={self.led},rate={self.rate},uptime={self.uptime}{CRLF}"
        if cmd == "LED":
            try:
                v = int(arg)
            except (TypeError, ValueError):
                return f"-ERR:2{CRLF}"
            if v not in LED_VALUES:
                return f"-ERR:3{CRLF}"
            self.led = v
            return f"+OK{CRLF}"
        if cmd == "RATE":
            try:
                v = int(arg)
            except (TypeError, ValueError):
                return f"-ERR:2{CRLF}"
            if not (RATE_MIN <= v <= RATE_MAX):
                return f"-ERR:3{CRLF}"
            self.rate = v
            return f"+OK{CRLF}"
        if cmd == "RESET":
            self.reset()
            return f"+OK{CRLF}"
        return f"-ERR:1{CRLF}"


class SerialDevice:
    """真实串口后端。pyserial 不是硬依赖——只有接真机时才需要。"""

    def __init__(self, port, baud=115200, timeout=0.3):
        try:
            import serial  # noqa: F401
        except ImportError:
            raise RuntimeError("接真机需要先 pip install pyserial")
        import serial as _s
        self._ser = _s.Serial(port=port, baudrate=baud, timeout=timeout)
        self._ser.reset_input_buffer()

    def write(self, data):
        self._ser.write(data)

    def readline(self, timeout=0.3):
        self._ser.timeout = timeout
        return self._ser.readline() or b""

    def reset(self):
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()

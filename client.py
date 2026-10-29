# -*- coding: utf-8 -*-
"""测试侧客户端：负责发命令、解析应答、重试、统计。

这一层是「测试框架」和「写脚本」的分界线——
重试策略、超时、时延统计、分支覆盖记录都收敛在这里，用例只管业务断言。
"""
import time

import protocol
from protocol import CRLF, FrameError


class Response:
    __slots__ = ("kind", "tag", "value", "raw", "err_code", "latency", "attempts")

    def __init__(self, kind, tag, value, raw, err_code, latency, attempts):
        self.kind = kind
        self.tag = tag
        self.value = value
        self.raw = raw
        self.err_code = err_code
        self.latency = latency
        self.attempts = attempts

    def __repr__(self):
        return f"<Response {self.kind} {self.tag}={self.value!r} err={self.err_code} {self.latency*1000:.1f}ms>"


class Stats:
    def __init__(self):
        self.latencies = []
        self.branches = set()
        self.sent = 0
        self.retries = 0
        self.timeouts = 0

    def pct(self, p):
        if not self.latencies:
            return 0.0
        xs = sorted(self.latencies)
        k = min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1))))
        return xs[k]

    def branch_coverage(self):
        hit = {b for b in self.branches if b in protocol.BRANCHES}
        return len(hit), len(protocol.BRANCHES), hit

    def summary(self):
        return {
            "sent": self.sent,
            "retries": self.retries,
            "timeouts": self.timeouts,
            "p50_ms": round(self.pct(50) * 1000, 2),
            "p95_ms": round(self.pct(95) * 1000, 2),
            "max_ms": round((max(self.latencies) if self.latencies else 0) * 1000, 2),
        }


class DeviceClient:
    def __init__(self, device, timeout=0.3, retries=2):
        self.dev = device
        self.timeout = timeout
        self.retries = retries
        self.stats = Stats()

    def send(self, cmd, arg=None, timeout=None, retries=None, raw=None):
        """发一条命令；超时或帧损坏时按策略重试。返回最后一次的 Response。

        raw 传入原始文本时不做协议封装，用于构造畸形帧做负向测试。
        """
        timeout = self.timeout if timeout is None else timeout
        retries = self.retries if retries is None else retries
        frame = raw if raw is not None else protocol.build(cmd, arg)
        last_exc = None

        for attempt in range(1, retries + 2):
            t0 = time.perf_counter()
            self.dev.write(frame.encode())
            self.stats.sent += 1
            try:
                raw = self.dev.readline(timeout)
                latency = time.perf_counter() - t0
                text = raw.decode("utf-8", "replace")
                if not text.endswith(CRLF):
                    raise FrameError("incomplete frame")
                kind, tag, value = protocol.parse(text)
                # 应答错位检测：tag 对不上说明链路串包或固件应答张冠李戴
                expect = protocol.EXPECTED_TAG.get(cmd)
                if kind == "ok" and expect and tag != expect:
                    raise FrameError(f"tag mismatch: want {expect}, got {tag}")
                err = value if kind == "err" else None
                self.stats.latencies.append(latency)
                # 成功分支按命令记；错误分支不区分命令，统一记在 * 下（错误码才是关注点）
                key = cmd if (kind == "ok" and cmd in protocol.EXPECTED_TAG) else "*"
                self.stats.branches.add((key, "ok" if kind == "ok" else f"err{err}"))
                return Response(kind, tag, value, text, err, latency, attempt)
            except FrameError as e:
                last_exc = e
                self.stats.retries += 1
                if attempt <= retries:
                    time.sleep(0.01)

        self.stats.timeouts += 1
        self.stats.branches.add(("*", "timeout"))
        raise TimeoutError(f"{cmd or raw!r}: {last_exc}") from last_exc

    def send_raw(self, text, **kw):
        """原样发送，不做 AT 封装——用于负向测试构造畸形帧。"""
        return self.send("", raw=text, **kw)

    # ---------- 语义化断言（失败信息要能直接定位） ----------
    def expect_ok(self, cmd, arg=None, **kw):
        r = self.send(cmd, arg, **kw)
        assert r.kind == "ok", f"{cmd}={arg} 期望成功，实际返回 -ERR:{r.err_code}"
        return r

    def expect_err(self, cmd, arg=None, code=None, **kw):
        r = self.send(cmd, arg, **kw)
        assert r.kind == "err", f"{cmd}={arg} 期望报错，实际成功: {r.raw!r}"
        if code is not None:
            assert r.err_code == code, f"{cmd}={arg} 期望 -ERR:{code}，实际 -ERR:{r.err_code}"
        return r

    def recover(self, max_attempts=3, timeout=0.3):
        """链路受扰后用 AT 探测，返回恢复所需次数；失败返回 None。"""
        for i in range(1, max_attempts + 1):
            try:
                r = self.send("AT", timeout=timeout, retries=0)
                if r.kind == "ok" and r.value == "READY":
                    return i
            except TimeoutError:
                pass
            time.sleep(0.02)
        return None

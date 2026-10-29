# -*- coding: utf-8 -*-
"""pytest 插件：汇总用例结果与链路统计，产出单文件 HTML 报告 + JSON。

设计原则：报告要能直接发给 HR / 面试官看，所以不依赖任何外部资源（无 CDN、无 JS 框架）。
"""
import datetime
import html
import json
import os

import protocol

from client import Stats

_RESULTS = []          # (nodeid, outcome, duration, longrepr)
_CLIENTS = []
_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def register(client):
    """用例通过 fixture 注册客户端，报告里统一汇总链路统计。"""
    _CLIENTS.append(client)


def aggregate():
    agg = Stats()
    for c in _CLIENTS:
        agg.sent += c.stats.sent
        agg.retries += c.stats.retries
        agg.timeouts += c.stats.timeouts
        agg.latencies.extend(c.stats.latencies)
        agg.branches |= c.stats.branches
    return agg


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _RESULTS.append({
            "nodeid": report.nodeid,
            "outcome": report.outcome,
            "duration": report.duration,
            "longrepr": str(report.longrepr)[:400] if report.failed else "",
        })


def _donut(passed, failed, skipped):
    total = max(1, passed + failed + skipped)
    r, c, w = 54, 60, 16
    circ = 2 * 3.141592653589793 * r
    segs, offset = [], 0.0
    for n, color in ((passed, "#111111"), (failed, "#c0392b"), (skipped, "#c9c9c9")):
        if not n:
            continue
        frac = n / total
        dash = frac * circ
        segs.append(
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{color}" stroke-width="{w}" '
            f'stroke-dasharray="{dash:.2f} {circ - dash:.2f}" stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {c} {c})"/>'
        )
        offset += dash
    rate = passed / total * 100
    return (
        f'<svg width="120" height="120" viewBox="0 0 120 120">{"".join(segs)}'
        f'<text x="60" y="57" text-anchor="middle" font-size="21" font-weight="bold" fill="#111">{rate:.1f}%</text>'
        f'<text x="60" y="74" text-anchor="middle" font-size="10" fill="#777">通过率</text></svg>'
    )


def _bars(rows):
    mx = max((r["total"] for r in rows), default=1)
    out = []
    for r in rows:
        pct = r["total"] / mx * 100
        ok = r["passed"] / max(1, r["total"]) * 100
        out.append(
            f'<div class="bar-row"><span class="bl">{html.escape(r["name"])}</span>'
            f'<span class="bt"><i style="width:{pct:.1f}%"><b style="width:{ok:.1f}%"></b></i></span>'
            f'<span class="bv">{r["passed"]}/{r["total"]}</span></div>'
        )
    return "".join(out)


def pytest_sessionfinish(session, exitstatus):
    os.makedirs(_OUT_DIR, exist_ok=True)
    agg = aggregate()
    hit, total_b, hit_set = agg.branch_coverage()

    passed = sum(1 for r in _RESULTS if r["outcome"] == "passed")
    failed = sum(1 for r in _RESULTS if r["outcome"] == "failed")
    skipped = sum(1 for r in _RESULTS if r["outcome"] == "skipped")

    # 按测试文件分组
    groups = {}
    for r in _RESULTS:
        name = r["nodeid"].split("::")[0].replace("tests/", "").replace(".py", "")
        g = groups.setdefault(name, {"name": name, "total": 0, "passed": 0})
        g["total"] += 1
        g["passed"] += 1 if r["outcome"] == "passed" else 0
    rows = sorted(groups.values(), key=lambda x: x["name"])

    s = agg.summary()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    case_rows = "".join(
        f'<tr class="{r["outcome"]}"><td class="ok-{r["outcome"]}">'
        f'{"PASS" if r["outcome"] == "passed" else ("FAIL" if r["outcome"] == "failed" else "SKIP")}</td>'
        f'<td>{html.escape(r["nodeid"].split("::", 1)[-1])}</td>'
        f'<td class="num">{r["duration"]*1000:.0f} ms</td></tr>'
        for r in _RESULTS
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>设备侧自动化回归测试 · 报告</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;padding:40px 32px;font:14px/1.65 "Microsoft YaHei",system-ui,sans-serif;color:#111;background:#fff}}
.wrap{{max-width:940px;margin:0 auto}}
h1{{font-size:24px;margin:0 0 4px}}
.sub{{color:#777;font-size:13px;margin-bottom:28px}}
.cards{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:28px}}
.card{{flex:1 1 150px;border:1px solid #e6e6e6;border-radius:10px;padding:14px 16px}}
.card b{{display:block;font-size:23px;letter-spacing:-.5px}}
.card span{{color:#777;font-size:12px}}
h2{{font-size:15px;margin:30px 0 12px;padding-left:8px;border-left:3px solid #111}}
.bar-row{{display:flex;align-items:center;gap:12px;margin-bottom:9px;font-size:13px}}
.bl{{width:210px;color:#333}}
.bt{{flex:1;height:9px;background:#f0f0f0;border-radius:5px;overflow:hidden;display:block}}
.bt i{{display:block;height:100%;background:#dcdcdc;border-radius:5px}}
.bt b{{display:block;height:100%;background:#111;border-radius:5px}}
.bv{{width:56px;text-align:right;color:#666;font-variant-numeric:tabular-nums}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;color:#888;font-weight:400;border-bottom:1px solid #e6e6e6;padding:8px 6px;font-size:12px}}
td{{padding:7px 6px;border-bottom:1px solid #f4f4f4}}
.num{{text-align:right;color:#888;font-variant-numeric:tabular-nums}}
.ok-pass{{color:#111;font-weight:bold}}
.ok-fail{{color:#c0392b;font-weight:bold}}
.ok-skipped{{color:#aaa}}
tr.failed td{{background:#fdf3f2}}
.legend{{display:flex;gap:16px;font-size:12px;color:#666;margin-top:8px}}
.dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}}
.foot{{margin-top:34px;color:#999;font-size:12px;border-top:1px solid #eee;padding-top:14px}}
</style></head><body><div class="wrap">
<h1>设备侧自动化回归测试 · 执行报告</h1>
<div class="sub">被测对象：串口设备固件（AT 指令协议）　·　执行时间 {now}</div>

<div class="cards">
  <div class="card"><b>{passed + failed + skipped}</b><span>用例总数</span></div>
  <div class="card"><b>{passed}</b><span>通过</span></div>
  <div class="card"><b>{failed}</b><span>失败</span></div>
  <div class="card"><b>{hit}/{total_b}</b><span>协议分支覆盖</span></div>
  <div class="card"><b>{s["p95_ms"]} ms</b><span>响应时延 P95</span></div>
</div>

<div style="display:flex;gap:26px;align-items:center">
  {_donut(passed, failed, skipped)}
  <div style="font-size:13px;color:#444;line-height:1.9">
    共发送命令 <b>{s["sent"]}</b> 条，重试 <b>{s["retries"]}</b> 次，链路超时 <b>{s["timeouts"]}</b> 次<br>
    响应时延：P50 <b>{s["p50_ms"]} ms</b>　P95 <b>{s["p95_ms"]} ms</b>　最大 <b>{s["max_ms"]} ms</b><br>
    已覆盖分支：{html.escape("、".join(sorted(f"{a}/{b}" for a, b in hit_set)))}
  </div>
</div>

<h2>各套件通过情况</h2>
{_bars(rows)}
<div class="legend"><span><i class="dot" style="background:#111"></i>通过</span>
<span><i class="dot" style="background:#dcdcdc"></i>未通过</span></div>

<h2>用例明细</h2>
<table><thead><tr><th style="width:70px">结果</th><th>用例</th><th style="width:90px;text-align:right">耗时</th></tr></thead>
<tbody>{case_rows}</tbody></table>

<div class="foot">由 pytest 插件自动生成　·　无外部依赖，单文件可直接分发</div>
</div></body></html>"""

    with open(os.path.join(_OUT_DIR, "report.html"), "w", encoding="utf-8") as f:
        f.write(html_doc)

    with open(os.path.join(_OUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({
            "total": passed + failed + skipped, "passed": passed, "failed": failed, "skipped": skipped,
            "branch_hit": hit, "branch_total": total_b, "link": s,
            "branches_hit": sorted(f"{a}/{b}" for a, b in hit_set),
            "branches_missing": sorted(f"{a}/{b}" for a, b in (protocol.BRANCHES - hit_set)),
        }, f, ensure_ascii=False, indent=2)

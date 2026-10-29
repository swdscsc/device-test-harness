# -*- coding: utf-8 -*-
import os

import pytest

import report
from client import DeviceClient
from device import SerialDevice, SimDevice


def pytest_configure(config):
    if not config.pluginmanager.has_plugin("devreport"):
        config.pluginmanager.register(report, "devreport")


@pytest.fixture
def make_client():
    """构造客户端。

    默认用 SimDevice（无需硬件）；设置环境变量 DUT_PORT=COM3 即切到真串口，
    同一套用例直接跑在真板子上——这是这个框架最重要的一个设计。
    """
    def _make(faults=None, seed=20261029, timeout=0.3, retries=2):
        port = os.environ.get("DUT_PORT")
        if port:
            dev = SerialDevice(port, baud=int(os.environ.get("DUT_BAUD", "115200")), timeout=timeout)
        else:
            dev = SimDevice(seed=seed, faults=faults)
        c = DeviceClient(dev, timeout=timeout, retries=retries)
        report.register(c)
        return c
    return _make


@pytest.fixture
def client(make_client):
    return make_client()

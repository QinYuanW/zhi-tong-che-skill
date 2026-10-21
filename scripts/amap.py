#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高德地图调用封装（地理编码 + 驾车路径规划）。

被两处使用：
  build_geo.py  —— 批量预计算，写入 route_duration
  query_bus.py  —— --live 模式下，库里查不到时实时补算

Key 读取优先级：环境变量 AMAP_KEY > data/amap_key.txt
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
KEY_FILE = BASE / "data" / "amap_key.txt"

GEO_URL = "https://restapi.amap.com/v3/geocode/geo"
DRIVE_URL = "https://restapi.amap.com/v3/direction/driving"
QPS_SLEEP = 0.35

# 地理编码纠偏：业务地名不足以让高德准确定位时，用完整地址覆盖。
# 踩过的坑：
#   「共青」→ 贵州省遵义市播州区共青（导致所有共青线路算出 800+ 分钟）
#   「寻乌筠门岭」→ 寻乌县城（筠门岭镇在更南边，会少算 40km）
ADDRESS_OVERRIDE = {
    "共青": "江西省九江市共青城市",
    "寻乌筠门岭": "江西省赣州市寻乌县筠门岭镇",
}


def load_key() -> str:
    env = os.environ.get("AMAP_KEY", "").strip()
    if env:
        return env
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def _get(url: str, params: dict, retries: int = 3) -> dict:
    qs = urllib.parse.urlencode(params)
    last_err = ""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(f"{url}?{qs}", timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            time.sleep(1.0 * (attempt + 1))
    return {"status": "0", "info": f"请求失败: {last_err}"}


def geocode(key: str, name: str) -> tuple[float, float, str] | None:
    """地名 → (经度, 纬度, 格式化地址)。失败返回 None。"""
    query = ADDRESS_OVERRIDE.get(name, name)
    data = _get(GEO_URL, {"address": query, "key": key})
    if data.get("status") != "1":
        return None
    items = data.get("geocodes") or []
    if not items:
        return None
    g = items[0]
    lng, lat = g["location"].split(",")
    return float(lng), float(lat), g.get("formatted_address", "")


def driving_minutes(key: str, origin_lnglat: str,
                    dest_lnglat: str) -> tuple[int, int] | None:
    """坐标 → (分钟, 公里)。失败返回 None。"""
    data = _get(DRIVE_URL, {
        "origin": origin_lnglat, "destination": dest_lnglat,
        "extensions": "base", "strategy": "0", "key": key,
    })
    if data.get("status") != "1":
        return None
    paths = (data.get("route") or {}).get("paths") or []
    if not paths:
        return None
    p = paths[0]
    return int(int(p["duration"]) / 60), int(int(p["distance"]) / 1000)


def lnglat(coord: tuple[float, float]) -> str:
    return f"{coord[0]:.6f},{coord[1]:.6f}"

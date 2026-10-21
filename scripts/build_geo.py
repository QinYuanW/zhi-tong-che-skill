#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用高德地图批量预计算线路车程。

    python scripts/build_geo.py --key 你的高德Key
    python scripts/build_geo.py --key xxx --limit 5      # 先跑 5 条试水
    python scripts/build_geo.py --key xxx --dry-run      # 只看要调多少次

规则：
1. 先地理编码把 35 个地名转成经纬度，存 locations 表（只算一次，之后复用）。
2. 再对库里实际存在的 (出发, 到达) 组合调驾车路径规划，存 route_duration。
3. **绝不覆盖 source='manual' 的记录** —— 你亲眼看的比接口准。
4. 存的是导航原始分钟数，+30 分钟缓冲由 query_bus.py 在展示层加。

Key 申请：https://lbs.amap.com/ → 控制台 → 应用管理 → 创建应用 → 添加 Key（选「Web服务」）
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query_bus import DB_PATH  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GEO_URL = "https://restapi.amap.com/v3/geocode/geo"
DRIVE_URL = "https://restapi.amap.com/v3/direction/driving"
QPS_SLEEP = 0.35  # 个人 Key 有频率限制，慢一点稳

# Key 读取优先级：命令行 > 环境变量 > data/amap_key.txt
KEY_FILE = DB_PATH.parent / "amap_key.txt"

# 地理编码纠偏：业务地名不足以让高德准确定位时，用完整地址覆盖。
# 已踩过的坑：
#   「共青」被匹配到 贵州省遵义市播州区共青 → 导致所有共青线路算出 800+ 分钟
#   「寻乌筠门岭」被匹配到寻乌县城 → 筠门岭镇在县城南约 40km，会少算
ADDRESS_OVERRIDE = {
    "共青": "江西省九江市共青城市",
    "寻乌筠门岭": "江西省赣州市寻乌县筠门岭镇",
}


def load_key(cli_key: str) -> str:
    if cli_key:
        return cli_key.strip()
    import os
    env = os.environ.get("AMAP_KEY", "").strip()
    if env:
        return env
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def http_get(url: str, params: dict, retries: int = 3) -> dict:
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
    query = ADDRESS_OVERRIDE.get(name, name)
    data = http_get(GEO_URL, {"address": query, "key": key})
    if data.get("status") != "1":
        print(f"  ✗ {name}: {data.get('info')}")
        return None
    items = data.get("geocodes") or []
    if not items:
        print(f"  ✗ {name}: 无匹配地址")
        return None
    g = items[0]
    lng, lat = g["location"].split(",")
    return float(lng), float(lat), g.get("formatted_address", "")


def driving_minutes(key: str, origin: str, destination: str) -> tuple[int, int] | None:
    data = http_get(DRIVE_URL, {
        "origin": origin, "destination": destination,
        "extensions": "base", "strategy": "0", "key": key,
    })
    if data.get("status") != "1":
        print(f"    路径规划失败: {data.get('info')}")
        return None
    paths = (data.get("route") or {}).get("paths") or []
    if not paths:
        print("    无可用路径")
        return None
    p = paths[0]
    return int(int(p["duration"]) / 60), int(int(p["distance"]) / 1000)


def main() -> None:
    ap = argparse.ArgumentParser(description="高德批量预计算车程")
    ap.add_argument("--key", default="", help="高德 Web 服务 Key（也可用环境变量 AMAP_KEY）")
    ap.add_argument("--limit", type=int, default=0, help="本次最多处理多少条组合")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不调接口")
    ap.add_argument("--refresh", action="store_true",
                    help="清空接口算出的车程与坐标后全部重算（人工记录保留）")
    args = ap.parse_args()

    key = load_key(args.key)
    if not key and not args.dry_run:
        print("缺少高德 Key。三种放法，任选其一：\n")
        print(f"  1) 写文件（推荐，只需一次）：")
        print(f"     {KEY_FILE}")
        print(f"     文件里只放那一行 Key，不要引号不要空格\n")
        print(f"  2) 环境变量：set AMAP_KEY=你的Key")
        print(f"  3) 命令行：python scripts/build_geo.py --key 你的Key")
        sys.exit(2)

    if not DB_PATH.exists():
        print(f"数据库不存在：{DB_PATH}\n请先运行 scripts/build_db.py")
        sys.exit(2)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            name        TEXT PRIMARY KEY,
            lng         REAL NOT NULL,
            lat         REAL NOT NULL,
            formatted   TEXT DEFAULT '',
            updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )""")

    # dry-run 不允许改动数据
    if args.refresh and not args.dry_run:
        con.execute("DELETE FROM route_duration WHERE source='amap'")
        con.execute("DELETE FROM locations")
        con.commit()
        print("已清空接口数据，将全部重算（人工录入的记录保留）\n")

    places = [r["n"] for r in con.execute(
        "SELECT DISTINCT origin AS n FROM routes "
        "UNION SELECT DISTINCT destination FROM routes ORDER BY n")]
    pairs = con.execute(
        "SELECT DISTINCT origin, destination FROM routes ORDER BY origin, destination").fetchall()

    have_geo = {r["name"] for r in con.execute("SELECT name FROM locations")}
    to_geo = [p for p in places if p not in have_geo]
    manual = {(r["origin"], r["destination"]) for r in con.execute(
        "SELECT origin, destination FROM route_duration WHERE source='manual'")}
    have_amap = {(r["origin"], r["destination"]) for r in con.execute(
        "SELECT origin, destination FROM route_duration WHERE source='amap'")}
    to_drive = [p for p in pairs
                if (p["origin"], p["destination"]) not in manual
                and (p["origin"], p["destination"]) not in have_amap]

    print(f"地名 {len(places)} 个（待编码 {len(to_geo)}）")
    print(f"线路组合 {len(pairs)} 条（待计算 {len(to_drive)}，人工已录 {len(manual)} 条自动跳过）")
    if args.dry_run:
        print("\n[dry-run] 预计接口调用："
              f"{len(to_geo)} 次地理编码 + {len(to_drive)} 次路径规划")
        con.close()
        return
    print()

    # 1. 地理编码
    for i, name in enumerate(to_geo, 1):
        res = geocode(key, name)
        if res:
            lng, lat, fmt = res
            con.execute(
                "INSERT INTO locations (name,lng,lat,formatted) VALUES (?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET lng=excluded.lng, lat=excluded.lat, "
                "formatted=excluded.formatted, updated_at=CURRENT_TIMESTAMP",
                (name, lng, lat, fmt))
            print(f"  [{i}/{len(to_geo)}] {name} → {fmt} ({lng},{lat})")
        time.sleep(QPS_SLEEP)
    con.commit()

    # 2. 路径规划
    coords = {r["name"]: (r["lng"], r["lat"]) for r in con.execute(
        "SELECT name, lng, lat FROM locations")}
    todo = to_drive[: args.limit] if args.limit else to_drive
    ok = fail = 0
    for i, row in enumerate(todo, 1):
        o, d = row["origin"], row["destination"]
        if o not in coords or d not in coords:
            continue
        oc, dc = coords[o], coords[d]
        res = driving_minutes(key, f"{oc[0]:.6f},{oc[1]:.6f}", f"{dc[0]:.6f},{dc[1]:.6f}")
        if res:
            minutes, km = res
            con.execute(
                "INSERT INTO route_duration (origin,destination,nav_minutes,source,note) "
                "VALUES (?,?,?,'amap',?) "
                "ON CONFLICT(origin,destination) DO UPDATE SET "
                "nav_minutes=excluded.nav_minutes, source='amap', "
                "note=excluded.note, updated_at=CURRENT_TIMESTAMP",
                (o, d, minutes, f"高德驾车 {km}km"))
            print(f"  [{i}/{len(todo)}] {o} → {d}: {minutes} 分钟（{km}km）")
            ok += 1
        else:
            print(f"  [{i}/{len(todo)}] {o} → {d}: 失败")
            fail += 1
        time.sleep(QPS_SLEEP)
        if i % 20 == 0:
            con.commit()

    con.commit()
    total = con.execute("SELECT COUNT(*) c FROM route_duration").fetchone()["c"]
    print(f"\n✓ 完成：成功 {ok} 条，失败 {fail} 条，车程表共 {total} 条")
    print(f"  对外答复会统一在导航时间上 +30 分钟（query_bus.py 的 BUFFER_MINUTES）")
    con.close()


if __name__ == "__main__":
    main()

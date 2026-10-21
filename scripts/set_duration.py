#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
录制线路车程（导航软件显示的时间）。

业务惯例：对外回答 = 导航时间 + 30 分钟缓冲。
所以这里**只存导航原始时间**，加缓冲的事交给 query_bus.py，
以后规则变了改一个常量就行，不用重录 300 条。

用法：
    # 单条录入（导航显示 2 小时 40 分 = 160 分钟）
    python scripts/set_duration.py --from 景德镇 --to 宁都 --minutes 160

    # 从 CSV 批量导入（格式：origin,destination,minutes，无表头）
    python scripts/set_duration.py --import durations.csv

    # 看看录了哪些
    python scripts/set_duration.py --list
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query_bus import DB_PATH, resolve_place  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BUFFER_MINUTES = 30


def fmt(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h} 小时 {m} 分" if h else f"{m} 分"


def normalize(con, name: str) -> str:
    info = resolve_place(con, name)
    if info.get("ambiguous"):
        print(f"⚠ 「{name}」有歧义（{'、'.join(info['clusters'])}），请写明确的统称")
        sys.exit(1)
    return info["clusters"][0] if info["clusters"] else name


def upsert(con, origin: str, destination: str, minutes: int,
           source: str = "manual", note: str = "") -> None:
    con.execute(
        "INSERT INTO route_duration (origin,destination,nav_minutes,source,note) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(origin,destination) DO UPDATE SET "
        "nav_minutes=excluded.nav_minutes, source=excluded.source, "
        "note=excluded.note, updated_at=CURRENT_TIMESTAMP",
        (origin, destination, minutes, source, note),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="录入线路车程")
    ap.add_argument("--from", dest="origin")
    ap.add_argument("--to", dest="destination")
    ap.add_argument("--minutes", type=int, help="导航软件显示的分钟数")
    ap.add_argument("--import", dest="csv_file", help="CSV 批量导入：origin,destination,minutes")
    ap.add_argument("--list", action="store_true", help="列出已录数据")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"数据库不存在：{DB_PATH}\n请先运行 scripts/build_db.py")
        sys.exit(2)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    if args.list:
        rows = con.execute(
            "SELECT origin,destination,nav_minutes,source,updated_at "
            "FROM route_duration ORDER BY origin,destination").fetchall()
        total = con.execute("SELECT COUNT(*) c FROM route_duration").fetchone()["c"]
        print(f"已录 {total} 条车程：\n")
        print(f"{'出发':<8}{'到达':<10}{'导航':<12}{'对外答复':<14}{'来源'}")
        for r in rows[:80]:
            nav = fmt(r["nav_minutes"])
            out = fmt(r["nav_minutes"] + BUFFER_MINUTES)
            print(f"{r['origin']:<8}{r['destination']:<10}{nav:<12}{out:<14}{r['source']}")
        if total > 80:
            print(f"... 其余 {total - 80} 条略")
        con.close()
        return

    if args.csv_file:
        path = Path(args.csv_file)
        if not path.exists():
            print(f"文件不存在：{path}")
            sys.exit(2)
        n = 0
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if len(row) < 3 or not row[2].strip():
                    continue
                o, d, m = row[0].strip(), row[1].strip(), int(float(row[2]))
                upsert(con, normalize(con, o), normalize(con, d), m, source="manual")
                n += 1
        con.commit()
        print(f"✓ 导入 {n} 条车程（对外答复会在导航时间上 +{BUFFER_MINUTES} 分钟）")
        con.close()
        return

    if not (args.origin and args.destination and args.minutes):
        ap.print_help()
        sys.exit(1)

    origin = normalize(con, args.origin)
    destination = normalize(con, args.destination)
    upsert(con, origin, destination, args.minutes)
    con.commit()

    print(f"✓ {origin} → {destination}")
    print(f"  导航显示   {fmt(args.minutes)}")
    print(f"  对外答复   约 {fmt(args.minutes + BUFFER_MINUTES)}")
    con.close()


if __name__ == "__main__":
    main()

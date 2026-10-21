#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标记线路的实际开通状态。

背景：build_db.py 里的数据是「排班计划」，不等于「小程序上真的能买」。
你在小程序后台核对完，用这个脚本把情况记下来，Agent 回答时就能区分
「排了班但没确认」和「确认能买」和「本期停了」。

用法：
    # 看哪些还没核对
    python scripts/mark_status.py --list --status planned

    # 确认某条线路可买
    python scripts/mark_status.py --set confirmed --from 景德镇 --to 宁都 --date 9-30

    # 整个日期批次都确认过了
    python scripts/mark_status.py --set confirmed --date 9-30

    # 某条线路本期停运
    python scripts/mark_status.py --set suspended --from 鹰潭 --to 兴国 --date 10-1

    # 撤销标记回到未确认
    python scripts/mark_status.py --set planned --date 10-1
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from query_bus import DB_PATH, normalize_date, resolve_place  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VALID = ("planned", "confirmed", "suspended")


def main() -> None:
    ap = argparse.ArgumentParser(description="标记线路开通状态")
    ap.add_argument("--set", choices=VALID, help="要设置的状态")
    ap.add_argument("--list", action="store_true", help="列出线路状态")
    ap.add_argument("--status", choices=VALID, help="配合 --list 过滤")
    ap.add_argument("--from", dest="origin", help="出发地（支持口语）")
    ap.add_argument("--to", dest="destination", help="目的地")
    ap.add_argument("--date", help="日期，如 9-30")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"数据库不存在：{DB_PATH}\n请先运行 scripts/build_db.py")
        sys.exit(2)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    date = normalize_date(args.date) if args.date else None
    origin = None
    destination = None
    if args.origin:
        info = resolve_place(con, args.origin)
        origin = info["clusters"][0] if info["clusters"] else args.origin
    if args.destination:
        info = resolve_place(con, args.destination)
        destination = info["clusters"][0] if info["clusters"] else args.destination

    where, params = ["1=1"], []
    if origin:
        where.append("origin = ?")
        params.append(origin)
    if destination:
        where.append("destination = ?")
        params.append(destination)
    if date:
        where.append("date = ?")
        params.append(date)
    cond = " AND ".join(where)

    # ---------- 列表 ----------
    if args.list or not args.set:
        extra = ""
        if args.status:
            extra = " AND status = ?"
            params2 = params + [args.status]
        else:
            params2 = params
        rows = con.execute(
            f"SELECT origin,destination,date,period,status FROM routes "
            f"WHERE {cond}{extra} ORDER BY date, origin LIMIT 60", params2).fetchall()
        total = con.execute(
            f"SELECT COUNT(*) c FROM routes WHERE {cond}{extra}", params2).fetchone()["c"]

        print(f"共 {total} 条，显示前 {len(rows)} 条：\n")
        print(f"{'日期':<12}{'出发':<8}{'到达':<10}{'时段':<6}{'状态'}")
        for r in rows:
            print(f"{r['date']:<12}{r['origin']:<8}{r['destination']:<10}"
                  f"{r['period']:<6}{r['status']}")
        if not args.status:
            print("\n状态分布：")
            for row in con.execute(
                    f"SELECT status, COUNT(*) c FROM routes WHERE {cond} GROUP BY status",
                    params):
                print(f"  {row['status']:<10}{row['c']} 条")
        con.close()
        return

    # ---------- 设置 ----------
    count = con.execute(f"SELECT COUNT(*) c FROM routes WHERE {cond}", params).fetchone()["c"]
    if count == 0:
        print("没有匹配的线路，未做任何修改。请检查 --from / --to / --date")
        con.close()
        sys.exit(1)

    if count > 20:
        print(f"⚠ 将影响 {count} 条线路（范围较广，请确认是否真的要整批标记）")
        print(f"  条件：{cond}  {' '.join(str(p) for p in params)}")
        print(f"  目标状态：{args.set}")
        print("  确认无误请加 --yes 重新执行")
        if "--yes" not in sys.argv:
            con.close()
            sys.exit(1)

    con.execute(f"UPDATE routes SET status = ? WHERE {cond}", [args.set] + params)
    con.commit()
    print(f"✓ 已把 {count} 条线路标记为 {args.set}")
    con.close()


if __name__ == "__main__":
    main()

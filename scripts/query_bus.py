#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直通车班次查询（供 Agent 调用）

设计原则：
- 只做精确查询，不做语义猜测。猜错的代价是学生白跑一趟。
- 宁可返回「没查到 + 可用选项」，也不要编造班次。
- 输出 JSON，字段名自解释，便于模型直接组织话术。

用法示例：
    python query_bus.py --from 陶大 --to 宁都 --date 9-30
    python query_bus.py --from 景德镇 --date 2026-10-01
    python query_bus.py --to 宁都 --date 10-1 --all-origins
    python query_bus.py --alias 陶大
    python query_bus.py --clusters
    python query_bus.py --faq 优惠
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

# Windows 控制台默认 GBK，中文输出会乱码/抛 UnicodeEncodeError。
# 在脚本内一次性解决，避免调用方（模型/终端）每次手动设 PYTHONIOENCODING。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "data" / "bus.db"

# 业务兜底：库里是「排班计划」，不等于「实际可售」。
# 这条 notice 由脚本直接吐给模型，避免它只靠提示词自觉而忘记声明。
NOTICE = (
    "以上为排班安排（计划层面）。实际是否开通、是否有余票，必须让学生在小程序"
    "实时售票页自行确认。禁止向学生承诺「有票」「可以坐」「一定能走」。"
)

# 业务惯例：对外答复的车程 = 导航软件显示时间 + 30 分钟缓冲。
# 只在这里改一处，全库生效，不用重录数据。
BUFFER_MINUTES = 30

# 到达时间 = 发车时间 + 导航时间 + BUFFER_MINUTES + REST_MINUTES
# 第一个 30：车程缓冲（导航偏乐观，真实路况会慢）
# 第二个 30：服务区休息（中途停一次，学生必须知道，否则会以为车不停）
REST_MINUTES = 30

# 回答车程/到达时必须补的一句——学生不知道车会停，就容易算错时间。
REST_NOTE = "一般中途会在服务区休息 30 分钟。"


def fmt_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    if h and m:
        return f"约 {h} 小时 {m} 分"
    if h:
        return f"约 {h} 小时"
    return f"约 {m} 分钟"


# 发车时间缺失时的兜底：同一天同一时段内滚动发车，取中间值最有代表性。
# 知识库里 10-6 / 10-7 返校只写了「早上」，没有具体时刻。
PERIOD_DEFAULT = {
    "早上": "09:00",
    "上午": "10:00",
    "中午": "12:30",
    "下午": "15:00",
}

# 发车时间只能给「左右」时，必须补这句 —— 它把「估不准」变成「下单后就知道」。
DEPART_DISCLAIMER = (
    "小程序下单出票后，小程序上会显示具体的上车时间"
    "（出票一般在出发前一天）。"
)


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.strip().split(":")
    return int(h) * 60 + int(m)


def estimate_depart(window: str | None, period: str) -> tuple[str, str]:
    """估算代表发车时刻。返回 (HH:MM, 依据类型)。

    range_mid      有时段 → 取中间值
    period_default 无时刻 → 按时段兜底
    """
    if window and "-" in window:
        try:
            a, b = window.split("-", 1)
            mid = (_to_minutes(a) + _to_minutes(b)) // 2
            return f"{mid // 60}:{mid % 60:02d}", "range_mid"
        except (ValueError, AttributeError):
            pass
    return PERIOD_DEFAULT.get(period, "09:00"), "period_default"


def estimate_arrival(depart_hhmm: str, nav_minutes: int) -> tuple[str, int]:
    """估算到达时刻 = 发车 + 导航 + 车程缓冲 + 服务区休息。

    返回 (HH:MM, 跨天数)。跨天用于「次日 01:30」这类表述。
    """
    total = (_to_minutes(depart_hhmm) + nav_minutes
             + BUFFER_MINUTES + REST_MINUTES)
    day_offset, remain = divmod(total, 24 * 60)
    return f"{remain // 60}:{remain % 60:02d}", day_offset


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(json.dumps({
            "error": "数据库不存在",
            "hint": f"请先运行 scripts/build_db.py 生成 {DB_PATH}",
        }, ensure_ascii=False))
        sys.exit(2)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------------------
# 名称归一：学生口语 → 高校统称
# ------------------------------------------------------------
def resolve_place(con: sqlite3.Connection, name: str) -> dict:
    """把用户输入的校名/口语解析成高校统称。县域名原样返回。"""
    name = (name or "").strip()
    if not name:
        return {"input": name, "clusters": [], "kind": "empty"}

    # 1) 别名精确命中（可能命中多个统称 → 歧义）
    rows = con.execute(
        "SELECT DISTINCT cluster FROM campus_alias WHERE alias = ?", (name,)
    ).fetchall()
    if rows:
        clusters = [r["cluster"] for r in rows]
        return {
            "input": name,
            "clusters": clusters,
            "kind": "alias",
            "ambiguous": len(clusters) > 1,
            "note": "同一校名对应多个高校统称，需向用户确认校区" if len(clusters) > 1 else "",
        }

    # 2) 本身就是统称
    rows = con.execute(
        "SELECT DISTINCT cluster FROM campus_alias WHERE cluster = ?", (name,)
    ).fetchall()
    if rows:
        return {"input": name, "clusters": [name], "kind": "cluster"}

    # 3) 模糊匹配（仅做提示，不自动采用）
    rows = con.execute(
        "SELECT DISTINCT alias, cluster FROM campus_alias "
        "WHERE alias LIKE ? OR cluster LIKE ? LIMIT 8",
        (f"%{name}%", f"%{name}%"),
    ).fetchall()
    if rows:
        return {
            "input": name,
            "clusters": [],
            "kind": "fuzzy",
            "suggestions": [{"alias": r["alias"], "cluster": r["cluster"]} for r in rows],
            "note": "未精确匹配，以下为相近项，需与用户确认后再查",
        }

    # 4) 当作县域/未收录地名
    return {"input": name, "clusters": [name], "kind": "place"}


# ------------------------------------------------------------
# 日期归一
# ------------------------------------------------------------
def normalize_date(raw: str) -> str | None:
    """支持 2026-09-30 / 9-30 / 0930 / 9月30日 / 10.1。"""
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"[年月]", "-", s).replace("日", "").replace(".", "-").replace("/", "-")

    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    m = re.fullmatch(r"(\d{2})(\d{2})", s)
    if m:
        return f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    return None


# ------------------------------------------------------------
# 查询
# ------------------------------------------------------------
def query_routes(con, origin: str | None, destination: str | None,
                 date: str | None) -> list[dict]:
    sql = ("SELECT origin,destination,date,period,time_window,direction,"
           "promo,note,section,status FROM routes WHERE 1=1")
    args: list[str] = []
    if origin:
        sql += " AND origin = ?"
        args.append(origin)
    if destination:
        sql += " AND destination = ?"
        args.append(destination)
    if date:
        sql += " AND date = ?"
        args.append(date)
    sql += " ORDER BY date, CASE period WHEN '早上' THEN 1 WHEN '上午' THEN 2 " \
           "WHEN '中午' THEN 3 WHEN '下午' THEN 4 ELSE 5 END, origin"
    rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    for r in rows:
        t, kind = estimate_depart(r.get("time_window"), r.get("period"))
        r["depart_estimate"] = t
        r["depart_note"] = (
            f"实际发车时段 {r['time_window']}，此为中间值"
            if kind == "range_mid"
            else f"具体时刻未提供，按「{r.get('period')}」估算"
        )
    return rows


def _fetch_live(con, origin: str, destination: str) -> int | None:
    """实时调高德补算一条车程，成功则写回缓存。返回导航分钟数。"""
    from amap import driving_minutes, geocode, lnglat, load_key  # 延迟导入，保证默认查询不联网

    key = load_key()
    if not key:
        return None

    coords: dict[str, tuple[float, float]] = {}
    for name in (origin, destination):
        row = con.execute("SELECT lng, lat FROM locations WHERE name = ?", (name,)).fetchone()
        if row:
            coords[name] = (row["lng"], row["lat"])
            continue
        g = geocode(key, name)
        if g is None:
            return None
        lng, lat, fmt = g
        con.execute(
            "INSERT INTO locations (name,lng,lat,formatted) VALUES (?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET lng=excluded.lng, lat=excluded.lat, "
            "formatted=excluded.formatted, updated_at=CURRENT_TIMESTAMP",
            (name, lng, lat, fmt))
        coords[name] = (lng, lat)

    res = driving_minutes(key, lnglat(coords[origin]), lnglat(coords[destination]))
    if res is None:
        return None
    minutes, km = res
    con.execute(
        "INSERT INTO route_duration (origin,destination,nav_minutes,source,note) "
        "VALUES (?,?,?,'amap_live',?) "
        "ON CONFLICT(origin,destination) DO UPDATE SET "
        "nav_minutes=excluded.nav_minutes, source='amap_live', "
        "note=excluded.note, updated_at=CURRENT_TIMESTAMP",
        (origin, destination, minutes, f"高德实时 {km}km"))
    con.commit()
    return minutes


def query_duration(con, origin: str | None, destination: str | None,
                   live: bool = False) -> dict | None:
    """查车程。库里存导航原始时间，对外答复统一加 BUFFER_MINUTES。

    live=True 时，库里没有就实时调高德补算并写回缓存（越用越全）。
    """
    if not (origin and destination):
        return None

    row = con.execute(
        "SELECT nav_minutes, source FROM route_duration "
        "WHERE origin = ? AND destination = ?", (origin, destination)).fetchone()

    if row is None:
        if not live:
            return None
        minutes = _fetch_live(con, origin, destination)
        if minutes is None:
            return None
        nav, source = minutes, "amap_live"
    else:
        nav, source = row["nav_minutes"], row["source"]

    reply = nav + BUFFER_MINUTES
    return {
        "nav_minutes": nav,
        "reply_minutes": reply,
        "text": fmt_duration(reply),
        "basis": f"导航 {fmt_duration(nav)} + {BUFFER_MINUTES} 分钟缓冲",
        "source": source,
    }


def build_hints(con, origin, destination, date, routes) -> list[str]:
    hints: list[str] = []
    if routes:
        return hints

    if date:
        alt = con.execute(
            "SELECT DISTINCT date FROM routes WHERE origin=? AND destination=? "
            "ORDER BY date", (origin, destination)).fetchall()
        if alt:
            hints.append("该线路在以下日期有班次：" + "、".join(r["date"] for r in alt))

    if origin and destination:
        rev = con.execute(
            "SELECT COUNT(*) c FROM routes WHERE origin=? AND destination=?",
            (destination, origin)).fetchone()["c"]
        if rev:
            hints.append(f"反向线路（{destination} → {origin}）存在 {rev} 条，注意方向是否符合用户意图")

    if destination and not origin:
        org = con.execute(
            "SELECT DISTINCT origin FROM routes WHERE destination=? ORDER BY origin",
            (destination,)).fetchall()
        if org:
            hints.append("可出发的高校统称：" + "、".join(r["origin"] for r in org))

    if origin and not destination:
        dst = con.execute(
            "SELECT DISTINCT destination FROM routes WHERE origin=? ORDER BY destination",
            (origin,)).fetchall()
        if dst:
            hints.append("该出发地可到达：" + "、".join(r["destination"] for r in dst))

    if not hints:
        hints.append("库中无该组合。不要编造班次，应告知用户当前无此线路并建议联系客服确认")
    return hints


def main() -> None:
    ap = argparse.ArgumentParser(description="直通车班次查询")
    ap.add_argument("--from", dest="origin", help="出发地：高校口语/统称/县域")
    ap.add_argument("--to", dest="destination", help="目的地：县域/高校统称")
    ap.add_argument("--date", help="日期：2026-09-30 / 9-30 / 0930 / 9月30日")
    ap.add_argument("--alias", help="只解析名称归属，不查班次")
    ap.add_argument("--clusters", action="store_true", help="列出全部高校统称")
    ap.add_argument("--faq", help="按关键词检索 FAQ")
    ap.add_argument("--live", action="store_true",
                    help="库里没有车程时实时调高德补算（结果写回缓存）")
    ap.add_argument("--pretty", action="store_true", help="格式化输出")
    args = ap.parse_args()

    con = connect()
    out: dict = {}

    if args.clusters:
        rows = con.execute(
            "SELECT cluster, SUM(CASE WHEN alias_type<>'cluster' THEN 1 ELSE 0 END) AS n "
            "FROM campus_alias GROUP BY cluster ORDER BY cluster").fetchall()
        out = {"clusters": [{"name": r["cluster"], "aliases": r["n"]} for r in rows]}
        con.close()
        print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    if args.faq:
        rows = con.execute(
            "SELECT category,question,answer,source FROM faq "
            "WHERE question LIKE ? OR answer LIKE ? OR category LIKE ?",
            (f"%{args.faq}%", f"%{args.faq}%", f"%{args.faq}%")).fetchall()
        out = {"query": args.faq, "count": len(rows),
               "items": [dict(r) for r in rows]}
        con.close()
        print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    if args.alias:
        out = {"resolved": resolve_place(con, args.alias)}
        con.close()
        print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))
        return

    date = normalize_date(args.date) if args.date else None
    origin_info = resolve_place(con, args.origin) if args.origin else None
    dest_info = resolve_place(con, args.destination) if args.destination else None

    # 名称有歧义时不猜，直接让上层追问
    ambiguity = []
    for label, info in (("origin", origin_info), ("destination", dest_info)):
        if info and info.get("ambiguous"):
            ambiguity.append(f"{label}={info['input']} 对应多个统称：{'、'.join(info['clusters'])}")
        if info and info.get("kind") == "fuzzy" and not info.get("clusters"):
            ambiguity.append(f"{label}={info['input']} 未精确匹配，候选："
                             + "、".join(f"{s['alias']}({s['cluster']})"
                                         for s in info.get("suggestions", [])))

    origin = origin_info["clusters"][0] if origin_info and origin_info["clusters"] else None
    destination = dest_info["clusters"][0] if dest_info and dest_info["clusters"] else None

    # 有歧义时绝不替用户选边，直接交给上层追问
    if ambiguity:
        routes: list[dict] = []
        hints = ["存在名称歧义：先向用户确认具体校区/统称，确认前不要给出班次结论"]
    else:
        routes = query_routes(con, origin, destination, date)
        hints = build_hints(con, origin, destination, date, routes)

    out = {
        "query": {"origin": args.origin, "destination": args.destination,
                  "date": args.date},
        "resolved": {
            "origin": None if ambiguity else origin,
            "destination": None if ambiguity else destination,
            "date": date,
        },
        "found": bool(routes),
        "count": len(routes),
        "routes": routes,
        "ambiguity": ambiguity,
        "hints": hints,
    }

    duration = query_duration(con, origin, destination, live=args.live)
    if duration:
        out["duration"] = duration
        out["rest_notice"] = REST_NOTE
        # 到达时刻依赖具体班次的发车时间，所以挂在每条 route 上
        for r in routes:
            t, offset = estimate_arrival(r["depart_estimate"], duration["nav_minutes"])
            r["arrival"] = f"次日 {t}" if offset else t
    if routes:
        out["notice"] = NOTICE
        out["depart_disclaimer"] = DEPART_DISCLAIMER
        suspended = [r for r in routes if r.get("status") == "suspended"]
        if suspended:
            out["hints"] = hints + [
                f"其中 {len(suspended)} 条状态为 suspended（本期停运/未开通），"
                "应明确告知学生该班次本期没有，不要含糊带过"
            ]
    if args.date and date is None:
        out["error"] = f"无法解析日期：{args.date}"

    con.close()
    print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()

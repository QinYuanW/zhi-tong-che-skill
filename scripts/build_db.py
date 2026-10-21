#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直通车线路库构建脚本
从国庆高校直通车线路知识库（Markdown）整理为可直接查询的 SQLite 数据库。

用法：
    python build_db.py            # 生成 data/bus.db（覆盖）
    python build_db.py --stat     # 只统计不写库

设计要点：
1. routes 表以「出发地 / 目的地 / 日期 / 时段」四个维度索引，查询必须精确命中，不做模糊匹配。
2. campus_alias 表承载「高校统称 ↔ 真实校名 ↔ 学生口语」，这是整个系统的准确率命门。
3. season 字段预留期次（国庆 / 寒假 / 清明 / 五一），寒假数据可直接叠加，不用改表结构。
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "data" / "bus.db"

SEASON = "2026国庆"

# ============================================================
# 一、高校统称（业务口径，非官方名称）
# ============================================================
# 返乡：9.30 中午 12 所
H12 = ["九江", "共青", "南昌", "靖安", "安义", "抚州",
       "萍乡", "宜春", "新余", "景德镇", "上饶", "鹰潭"]
# 主流通用：14 所
H14 = ["九江", "共青", "南昌", "靖安", "安义", "丰城", "抚州",
       "萍乡", "宜春", "新余", "吉安", "景德镇", "上饶", "鹰潭"]
# 15 所（广昌 / 于都 返校时多赣州）
H15 = H14 + ["赣州"]

# ============================================================
# 二、线路数据
# ============================================================
ROUTES: list[tuple] = []


def add(origins, destinations, *, date, period, window="", direction="out",
        promo=None, note="", section=""):
    """批量写入线路。origins / destinations 可以是字符串或列表（笛卡尔积展开）。"""
    if isinstance(origins, str):
        origins = [origins]
    if isinstance(destinations, str):
        destinations = [destinations]
    for o in origins:
        for d in destinations:
            ROUTES.append((o, d, date, period, window, direction, promo, note, section, SEASON))


# ---------- 一.1  9月30日 中午 12:00-14:00（高校 → 县域） ----------
SEC = "一.1 9.30中午"
add(H12, "宁都", date="2026-09-30", period="中午", window="12:00-14:00", section=SEC)
add("景德镇", "广昌", date="2026-09-30", period="中午", window="12:00-14:00", section=SEC)
add("上饶", "广昌", date="2026-09-30", period="中午", window="12:00-14:00", section=SEC)
add("抚州", "广昌", date="2026-09-30", period="中午", window="12:00-14:00", section=SEC)
add(["共青", "抚州"], "乐平", date="2026-09-30", period="中午", window="12:00-14:00", section=SEC)
add(["共青", "抚州"], "景德镇", date="2026-09-30", period="中午", window="12:00-14:00", section=SEC)
add("抚州", ["瑞金", "会昌", "寻乌", "于都", "赣县", "赣州", "南康"],
    date="2026-09-30", period="中午", window="12:00-14:00", section=SEC)

# ---------- 一.2  9月30日 下午 16:30-18:30 ----------
# 注意：原表头为「出发县域 | 出发高校」，方向存疑，按原值录入并标注
SEC = "一.2 9.30下午"
NOTE_D2 = "原表头为「出发县域|出发高校」，方向待业务确认"
add("宁都", ["共青", "南昌", "抚州"], date="2026-09-30", period="下午",
    window="16:30-18:30", note=NOTE_D2, section=SEC)
add(["乐平", "景德镇"], "共青", date="2026-09-30", period="下午",
    window="16:30-18:30", note=NOTE_D2, section=SEC)
add(["乐平", "景德镇"], "抚州", date="2026-09-30", period="下午",
    window="16:30-18:30", note=NOTE_D2, section=SEC)

# ---------- 一.3  10月1日 早上 07:00-10:00（主线六大县域） ----------
SEC = "一.3 10.1早上主线"
add(H14, ["宁都", "瑞金", "会昌", "寻乌筠门岭", "于都", "广昌"],
    date="2026-10-01", period="早上", window="07:00-10:00", section=SEC)

# ---------- 一.3  10月1日 早上 其他县域 ----------
SEC = "一.3 10.1早上其他"
add(["共青", "抚州", "赣州"], "乐平", date="2026-10-01", period="早上",
    window="07:00-10:00", section=SEC)
add(["抚州", "共青", "九江", "南昌", "景德镇", "新余", "宜春", "萍乡"], "石城",
    date="2026-10-01", period="早上", window="07:00-10:00", section=SEC)
add(["共青", "抚州"], ["赣县", "赣州", "南康"], date="2026-10-01", period="早上",
    window="07:00-10:00", section=SEC)

# ---------- 一.4  10月1日 上午（特色线路） ----------
SEC = "一.4 10.1特色"
add("共青", ["高安", "上高", "铜鼓", "万载", "宜春", "抚州"],
    date="2026-10-01", period="上午", section=SEC)
add("上饶", ["赣县", "赣州", "南康"], date="2026-10-01", period="上午",
    promo="两人同行满减40", section=SEC)
add("景德镇", ["赣县", "赣州", "南康", "兴国"], date="2026-10-01", period="上午", section=SEC)
add(["鹰潭", "上饶"], "兴国", date="2026-10-01", period="上午", section=SEC)
add("抚州", ["信丰", "龙南"], date="2026-10-01", period="上午", section=SEC)
add("抚州", "兴国", date="2026-10-01", period="上午", promo="两人同行优惠60", section=SEC)

# ---------- 二.1  10月6日 早上（县域 → 高校） ----------
SEC = "二.1 10.6返校"
add(["宁都", "瑞金", "会昌", "寻乌"], H14, date="2026-10-06", period="早上",
    direction="back", section=SEC)

# ---------- 二.2  10月7日 早上（县域 → 高校） ----------
SEC = "二.2 10.7返校"
add(["宁都", "瑞金", "会昌", "寻乌筠门岭"], H14, date="2026-10-07", period="早上",
    direction="back", section=SEC)
add(["广昌", "于都"], H15, date="2026-10-07", period="早上", direction="back", section=SEC)
add("石城", ["抚州", "共青", "九江", "南昌", "景德镇"], date="2026-10-07",
    period="早上", direction="back", section=SEC)
add("乐平", ["共青", "抚州", "赣州"], date="2026-10-07", period="中午",
    direction="back", note="乐平为中午车次", section=SEC)
add(["赣县", "赣州", "南康"], ["共青", "抚州"], date="2026-10-07", period="早上",
    direction="back", section=SEC)


# ============================================================
# 三、高校别名（统称 / 官方校名 / 学生口语）
# ============================================================
# type: cluster=统称, official=官方校名, colloquial=学生口语
# verified: 1=知识库已确认, 0=待业务确认（口语部分需汤园补充）
ALIASES: list[tuple[str, str, str, int, str]] = [
    # ---- 南昌 ----
    ("南昌", "南昌高校", "cluster", 1, "南昌市"),
    ("南昌", "南昌大学", "official", 1, ""),
    ("南昌", "南昌大学(前湖)", "colloquial", 0, "待确认"),
    ("南昌", "江西师范大学", "official", 1, ""),
    ("南昌", "江西财经大学", "official", 1, ""),
    ("南昌", "江财", "colloquial", 1, "常用简称"),
    ("南昌", "江西农业大学", "official", 1, ""),
    ("南昌", "南昌航空大学", "official", 1, ""),
    ("南昌", "昌航", "colloquial", 0, "待确认"),
    ("南昌", "华东交通大学", "official", 1, ""),
    ("南昌", "华东交大", "colloquial", 1, "常用简称"),
    ("南昌", "江西科技师范大学", "official", 1, ""),
    ("南昌", "江西中医药大学", "official", 1, ""),
    ("南昌", "东华理工大学", "official", 1, "主校区南昌，抚州设校区"),
    ("南昌", "江西水利电力大学", "official", 1, "原南昌工程学院，2025更名"),
    ("南昌", "南昌工程学院", "colloquial", 1, "旧名，学生仍可能使用"),
    ("南昌", "江西警察学院", "official", 1, ""),
    ("南昌", "南昌医学院", "official", 1, ""),
    ("南昌", "南昌师范学院", "official", 1, ""),
    ("南昌", "豫章师范学院", "official", 1, ""),
    ("南昌", "江西飞行学院", "official", 1, "南昌/吉安双校区"),
    ("南昌", "江西科技学院", "official", 1, ""),
    ("南昌", "南昌理工学院", "official", 1, ""),
    ("南昌", "江西服装学院", "official", 1, ""),
    ("南昌", "南昌工学院", "official", 1, "共青城设校区"),
    ("南昌", "江西应用科技学院", "official", 1, ""),
    ("南昌", "南昌交通学院", "official", 1, "靖安设校区"),
    ("南昌", "南昌应用技术师范学院", "official", 1, "共青城设校区"),
    ("南昌", "江西软件职业技术大学", "official", 1, ""),
    ("南昌", "南昌科技职业大学", "official", 1, ""),
    ("南昌", "江西旅游商贸职业学院", "official", 1, ""),
    ("南昌", "江西现代职业技术学院", "official", 1, ""),
    ("南昌", "江西交通职业技术学院", "official", 1, ""),
    ("南昌", "江西机电职业技术学院", "official", 1, ""),
    ("南昌", "江西外语外贸职业学院", "official", 1, ""),
    ("南昌", "江西建设职业技术学院", "official", 1, ""),
    ("南昌", "江西卫生职业学院", "official", 1, ""),
    ("南昌", "江西司法警官职业学院", "official", 1, ""),
    ("南昌", "江西传媒职业学院", "official", 1, ""),
    ("南昌", "江西青年职业学院", "official", 1, "安义设校区"),
    ("南昌", "江西水利职业学院", "official", 1, ""),
    ("南昌", "江西艺术职业学院", "official", 1, ""),
    ("南昌", "江西生物科技职业学院", "official", 1, ""),
    ("南昌", "江西电力职业技术学院", "official", 1, ""),
    ("南昌", "江西工商职业技术学院", "official", 1, ""),
    ("南昌", "江西航空职业技术学院", "official", 1, "抚州设校区"),
    ("南昌", "南昌影视传播职业学院", "official", 1, ""),

    # ---- 共青（科教城） ----
    ("共青", "共青高校", "cluster", 1, "共青城市，属九江市"),
    ("共青", "南昌大学共青学院", "official", 1, ""),
    ("共青", "南昌大学科学技术学院", "official", 1, "校址共青城五四大道"),
    ("共青", "江西师范大学科学技术学院", "official", 1, "校址共青城青年大道"),
    ("共青", "江西农业大学南昌商学院", "official", 1, ""),
    ("共青", "南昌航空大学科技学院", "official", 1, ""),
    ("共青", "江西财经大学现代经济管理学院", "official", 1, ""),
    ("共青", "九江科技职业大学", "official", 1, "原共青科技职业学院，2025升格"),
    ("共青", "共青科技职业学院", "colloquial", 1, "旧名"),
    ("共青", "南昌工学院共青校区", "official", 1, "赣新校区"),
    ("共青", "南昌应用技术师范学院共青校区", "official", 1, "赣新校区"),

    # ---- 九江 ----
    ("九江", "九江高校", "cluster", 1, "九江市"),
    ("九江", "九江学院", "official", 1, ""),
    ("九江", "江西职业技术大学", "official", 1, "原九江职业技术学院，2025升格"),
    ("九江", "九江职业大学", "official", 1, ""),
    ("九江", "江西财经职业学院", "official", 1, ""),
    ("九江", "九江理工职业学院", "official", 1, ""),
    ("九江", "江西枫林涉外经贸职业学院", "official", 1, "校址永修县"),

    # ---- 景德镇 ----
    ("景德镇", "景德镇高校", "cluster", 1, "景德镇市"),
    ("景德镇", "景德镇陶瓷大学", "official", 1, ""),
    ("景德镇", "陶大", "colloquial", 0, "待确认"),
    ("景德镇", "景陶", "colloquial", 0, "待确认"),
    ("景德镇", "景德镇学院", "official", 1, ""),
    ("景德镇", "景德镇艺术职业大学", "official", 1, ""),
    ("景德镇", "江西陶瓷工艺美术职业技术学院", "official", 1, ""),
    ("景德镇", "景德镇陶瓷职业技术学院", "official", 1, ""),
    ("景德镇", "景德镇卫生健康职业学院", "official", 1, "2025设立"),

    # ---- 赣州 ----
    ("赣州", "赣州高校", "cluster", 1, "赣州市"),
    ("赣州", "江西理工大学", "official", 1, "主校区赣州，南昌设校区"),
    ("赣州", "赣南师范大学", "official", 1, ""),
    ("赣州", "赣南医科大学", "official", 1, "原赣南医学院"),
    ("赣州", "赣南医学院", "colloquial", 1, "旧名"),
    ("赣州", "赣南科技学院", "official", 1, ""),
    ("赣州", "赣南师范大学科技学院", "official", 1, ""),
    ("赣州", "江西应用技术职业学院", "official", 1, ""),
    ("赣州", "江西环境工程职业学院", "official", 1, ""),
    ("赣州", "赣州师范高等专科学校", "official", 1, ""),
    ("赣州", "赣南卫生健康职业学院", "official", 1, ""),
    ("赣州", "赣州职业技术学院", "official", 1, ""),
    ("赣州", "和君职业学院", "official", 1, ""),

    # ---- 上饶 ----
    ("上饶", "上饶高校", "cluster", 1, "上饶市"),
    ("上饶", "上饶师范学院", "official", 1, ""),
    ("上饶", "江西医学高等专科学校", "official", 1, ""),
    ("上饶", "上饶幼儿师范高等专科学校", "official", 1, ""),
    ("上饶", "上饶职业技术学院", "official", 1, ""),
    ("上饶", "江西婺源茶业职业学院", "official", 1, ""),
    ("上饶", "上饶卫生健康职业学院", "official", 1, ""),
    ("上饶", "鄱阳职业学院", "official", 1, "2025设立"),

    # ---- 宜春 ----
    ("宜春", "宜春高校", "cluster", 1, "宜春市"),
    ("宜春", "宜春学院", "official", 1, ""),
    ("宜春", "宜春职业技术学院", "official", 1, ""),
    ("宜春", "宜春幼儿师范高等专科学校", "official", 1, "校址高安市"),
    ("宜春", "江西农业工程职业学院", "official", 1, "校址樟树市"),
    ("宜春", "江西樟树中医药职业学院", "official", 1, "校址樟树市"),
    ("宜春", "江西洪州职业学院", "official", 1, "校址丰城市"),

    # ---- 吉安 ----
    ("吉安", "吉安高校", "cluster", 1, "吉安市"),
    ("吉安", "井冈山大学", "official", 1, ""),
    ("吉安", "吉安职业技术学院", "official", 1, ""),
    ("吉安", "吉安幼儿师范专科学校", "official", 1, ""),

    # ---- 抚州 ----
    ("抚州", "抚州高校", "cluster", 1, "抚州市"),
    ("抚州", "东华理工大学(抚州)", "official", 1, "东华理工抚州校区"),
    ("抚州", "赣东学院", "official", 1, "原东华理工长江学院转设"),
    ("抚州", "抚州医药学院", "official", 1, "2025新设"),
    ("抚州", "抚州职业技术学院", "official", 1, ""),
    ("抚州", "抚州幼儿师范高等专科学校", "official", 1, ""),
    ("抚州", "赣东职业技术学院", "official", 1, ""),

    # ---- 新余 ----
    ("新余", "新余高校", "cluster", 1, "新余市"),
    ("新余", "新余学院", "official", 1, ""),
    ("新余", "江西工程学院", "official", 1, ""),
    ("新余", "江西冶金职业技术学院", "official", 1, ""),
    ("新余", "赣西科技职业学院", "official", 1, ""),
    ("新余", "江西新能源科技职业学院", "official", 1, ""),

    # ---- 萍乡 ----
    ("萍乡", "萍乡高校", "cluster", 1, "萍乡市"),
    ("萍乡", "萍乡学院", "official", 1, ""),
    ("萍乡", "江西工业工程职业技术学院", "official", 1, ""),
    ("萍乡", "江西应用工程职业学院", "official", 1, ""),
    ("萍乡", "萍乡卫生职业学院", "official", 1, ""),

    # ---- 鹰潭 ----
    ("鹰潭", "鹰潭高校", "cluster", 1, "鹰潭市（无独立本科院校）"),
    ("鹰潭", "江西师范高等专科学校", "official", 1, ""),
    ("鹰潭", "鹰潭职业技术学院", "official", 1, ""),
    ("鹰潭", "鹰潭卫生职业学院", "official", 1, "2025设立"),

    # ---- 丰城 ----
    ("丰城", "丰城高校", "cluster", 1, "丰城市，属宜春市"),
    ("丰城", "江西洪州职业学院", "official", 1, ""),
    ("丰城", "丰城开放学院", "official", 1, "成人教育"),

    # ---- 靖安 ----
    ("靖安", "靖安高校", "cluster", 1, "靖安县，属宜春市"),
    ("靖安", "南昌交通学院靖安墨轩湖校区", "official", 1, "唯一办学点"),

    # ---- 安义 ----
    ("安义", "安义高校", "cluster", 1, "安义县，属南昌市"),
    ("安义", "南昌职业大学", "official", 1, "凤凰、香樟校区"),
    ("安义", "江西青年职业学院安义校区", "official", 1, ""),
    ("安义", "安义开放大学", "official", 1, "成人教育"),
]


# ============================================================
# 四、FAQ（政策类，直接进 prompt 也可，建表便于维护）
# ============================================================
FAQ: list[tuple[str, str, str, str]] = [
    ("优惠", "两人同行怎么优惠？",
     "上饶高校→赣县/赣州/南康：两人同行满减 40 元；抚州高校→兴国：两人同行优惠 60 元。"
     "其他线路暂无同行优惠，以当期公告为准。", "知识库六"),
    ("优惠", "优惠可以和别的活动叠加吗？",
     "待补充：需业务确认是否可与其他优惠叠加。", "待确认"),
    ("乘车", "在哪里上车？",
     "待补充：各高校具体上车点（校门口/指定集合点）需按当期通知，Agent 不应自行编造。", "待确认"),
    ("退改", "可以退票吗？提前多久？",
     "待补充：退改规则需业务方提供。", "待确认"),
    ("退改", "错过发车时间怎么办？",
     "待补充：需业务方提供处理口径。", "待确认"),
    ("行李", "行李能带多少？",
     "待补充：需业务方提供。", "待确认"),
    ("时段", "9月30日下午的车是从哪里出发的？",
     "该批次原表头为「出发县域|出发高校」，方向需业务确认后再对外答复。", "待确认"),
]


# ============================================================
# 五、建库
# ============================================================
SCHEMA = """
CREATE TABLE IF NOT EXISTS routes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    origin      TEXT NOT NULL,           -- 出发地（高校统称或县域）
    destination TEXT NOT NULL,           -- 目的地
    date        TEXT NOT NULL,           -- YYYY-MM-DD
    period      TEXT NOT NULL,           -- 早上/上午/中午/下午
    time_window TEXT DEFAULT '',         -- 如 12:00-14:00
    direction   TEXT NOT NULL,           -- out=返乡(校→县) back=返校(县→校)
    promo       TEXT DEFAULT '',         -- 同行优惠
    note        TEXT DEFAULT '',         -- 备注/存疑标记
    section     TEXT DEFAULT '',         -- 来源章节，便于回溯
    season      TEXT NOT NULL,           -- 期次，如 2026国庆
    -- 开通状态：本表是「排班计划」，不等于「实际可售」。
    -- planned   已排班（默认，绝大多数）
    -- confirmed 票务员在小程序已确认可下单
    -- suspended 本期停运/未开通
    status      TEXT NOT NULL DEFAULT 'planned',
    UNIQUE(origin, destination, date, period, direction)
);

CREATE INDEX IF NOT EXISTS idx_routes_od   ON routes(origin, destination);
CREATE INDEX IF NOT EXISTS idx_routes_date ON routes(date);
CREATE INDEX IF NOT EXISTS idx_routes_dest ON routes(destination);
-- 旧库没有 UNIQUE 约束，补一个唯一索引，让 upsert 的 ON CONFLICT 能命中
CREATE UNIQUE INDEX IF NOT EXISTS idx_routes_uniq
    ON routes(origin, destination, date, period, direction);

-- 车程时长：存「导航软件显示的时间」，不存加工后的结果。
-- 对外回答时统一在上面的基础上 +30 分钟（业务惯例，见 BUFFER_MINUTES）。
-- 单独建表且不随 build_db 重建，避免人工录入的数据被覆盖。
CREATE TABLE IF NOT EXISTS route_duration (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    origin       TEXT NOT NULL,
    destination  TEXT NOT NULL,
    nav_minutes  INTEGER NOT NULL,           -- 导航软件显示的驾车耗时
    source       TEXT NOT NULL DEFAULT 'manual',  -- manual=人工录入 / amap=接口预计算
    note         TEXT DEFAULT '',
    updated_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(origin, destination)
);

CREATE TABLE IF NOT EXISTS campus_alias (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster    TEXT NOT NULL,            -- 高校统称，如「景德镇」
    alias      TEXT NOT NULL,            -- 别名原文（同一校名可属多个统称，如江西洪州职业学院）
    alias_type TEXT NOT NULL,            -- cluster/official/colloquial
    verified   INTEGER NOT NULL DEFAULT 1,
    note       TEXT DEFAULT '',
    UNIQUE(alias, cluster)
);

CREATE INDEX IF NOT EXISTS idx_alias_name    ON campus_alias(alias);
CREATE INDEX IF NOT EXISTS idx_alias_cluster ON campus_alias(cluster);

CREATE TABLE IF NOT EXISTS faq (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    question TEXT NOT NULL,
    answer   TEXT NOT NULL,
    source   TEXT DEFAULT ''
);
"""


def build():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    # 别名按 (alias, cluster) 去重，保留先出现的
    seen: set[tuple[str, str]] = set()
    aliases: list[tuple] = []
    for row in ALIASES:
        key = (row[1], row[0])
        if key in seen:
            continue
        seen.add(key)
        aliases.append(row)

    # routes 用 upsert：刷新内容，但绝不覆盖 status（人工资讯标记必须保留）
    con.executemany(
        "INSERT INTO routes (origin,destination,date,period,time_window,direction,"
        "promo,note,section,season,status) VALUES (?,?,?,?,?,?,?,?,?,?,'planned') "
        "ON CONFLICT(origin,destination,date,period,direction) DO UPDATE SET "
        "time_window=excluded.time_window, promo=excluded.promo, note=excluded.note, "
        "section=excluded.section, season=excluded.season",
        ROUTES,
    )
    con.executemany(
        "INSERT OR IGNORE INTO campus_alias (cluster,alias,alias_type,verified,note) "
        "VALUES (?,?,?,?,?)",
        aliases,
    )
    # faq 为静态数据、无人工状态，整表替换
    con.execute("DELETE FROM faq")
    con.executemany(
        "INSERT INTO faq (category,question,answer,source) VALUES (?,?,?,?)",
        FAQ,
    )
    con.commit()

    cur = con.cursor()
    n_routes = cur.execute("SELECT COUNT(*) FROM routes").fetchone()[0]
    n_alias = cur.execute("SELECT COUNT(*) FROM campus_alias").fetchone()[0]
    n_faq = cur.execute("SELECT COUNT(*) FROM faq").fetchone()[0]
    n_pending = cur.execute(
        "SELECT COUNT(*) FROM campus_alias WHERE verified=0").fetchone()[0]

    print(f"数据库：{DB_PATH}")
    print(f"  线路      {n_routes} 条")
    print(f"  别名      {n_alias} 条（其中 {n_pending} 条待确认）")
    print(f"  FAQ       {n_faq} 条")
    n_dur = cur.execute("SELECT COUNT(*) FROM route_duration").fetchone()[0]
    print(f"  车程      {n_dur} 条")
    print()
    print("开通状态：")
    for st, cnt in cur.execute(
            "SELECT status, COUNT(*) FROM routes GROUP BY status ORDER BY status"):
        print(f"  {st:<10}{cnt} 条")
    print()
    print("按日期分布：")
    for date, cnt in cur.execute(
            "SELECT date, COUNT(*) FROM routes GROUP BY date ORDER BY date"):
        print(f"  {date}  {cnt:>4} 条")
    con.close()

    return n_routes, n_alias, n_faq


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stat", action="store_true", help="只统计不写库")
    args = ap.parse_args()
    if args.stat:
        print(f"待写入：{len(ROUTES)} 条线路 / {len(ALIASES)} 条别名 / {len(FAQ)} 条FAQ")
    else:
        build()

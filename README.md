# zhi-tong-che · 直通车查票技能

给 nanobot 用的江西高校直通车班次查询技能。**不修改 nanobot 任何源码**，纯增量扩展。

## 这是什么

一个标准 nanobot 技能包（`SKILL.md` + 脚本 + 数据），放到 `~/.nanobot/workspace/skills/` 即可被 Agent 自动加载。

Agent 收到学生问「景德镇能回宁都吗」时，会按 `SKILL.md` 的指示调用 `query_bus.py` 查 SQLite，拿到结构化结果再组织话术。

## 为什么不是纯 RAG

知识库是**二维时刻表矩阵**（出发地 × 目的地 × 日期 × 时段 × 方向 × 优惠），不是散文。
纯向量检索会漏行、编造发车时间、答错优惠条件。所以这里走「精确查询 + 模型只负责话术」：

```
学生提问 → 口语归一到统称 → SQL 精确命中 → 模型组织回答
```

## 目录

```
zhi-tong-che/
├── SKILL.md              技能说明（Agent 读这个）
├── README.md             本文档
├── data/
│   └── bus.db            SQLite：routes / campus_alias / faq
└── scripts/
    ├── build_db.py       从知识库重建数据库
    └── query_bus.py      查询脚本（Agent 调用）
```

## 安装

```bash
# 复制到 nanobot 技能目录
xcopy /E /I "D:\Demo\projects\直通车\skills\zhi-tong-che" ^
  "%USERPROFILE%\.nanobot\workspace\skills\zhi-tong-che"
```

重启 nanobot 后生效。

## 手动测试

```bash
cd %USERPROFILE%\.nanobot\workspace\skills\zhi-tong-che

python scripts\query_bus.py --from 陶大 --to 宁都 --date 9-30
python scripts\query_bus.py --from 南昌 --to 宁都 --date 10-1
python scripts\query_bus.py --to 宁都 --date 10-1
python scripts\query_bus.py --alias 陶大
python scripts\query_bus.py --clusters
python scripts\query_bus.py --faq 优惠
```

## 当前数据规模

- 线路 **308** 条（9-30：33 / 10-1：119 / 10-6：56 / 10-7：100）
- 别名 **137** 条（含 4 条待确认为学生口语）
- FAQ **7** 条（其中 5 条标「待补充」，需业务方填）

## 待你补的东西

这几项只有你知道，我不该替你编：

1. **学生真实口语别名** —— 现在标 `verified=0` 的 4 条（陶大、景陶、昌航、南昌大学(前湖)），每个统称建议补 3–5 个
2. **上车点** —— 各高校具体集合位置
3. **退改规则** —— 提前多久可退、怎么退、错过发车怎么办
4. **行李额度**
5. **9-30 下午那批车的方向** —— 原表头是「出发县域|出发高校」，需确认是返乡还是返校

补完后重跑 `build_db.py` 即可，不用改任何代码。

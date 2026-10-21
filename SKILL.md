---
name: zhi-tong-che
display_name: 直通车查票
display_name_en: Campus Shuttle Query
description: 江西高校直通车班次查询。当用户询问某高校到某县域有没有班车、几点发车、返乡或返校车次、两人同行优惠时使用。含 308 条线路、137 条院校别名、7 条政策 FAQ 的本地 SQLite 精确查询能力。
category: business
version: 1.0.0
author: 汤园
metadata: {"nanobot":{"emoji":"🚌","requires":{"bins":["python"]}}}
---

# 江西高校直通车

校园直通车售票业务，覆盖江西省内 15 个高校统称、20+ 个县域。
所有班次存在本地 SQLite，**必须查库，不许凭印象回答**。

## 数据位置

本技能目录下：

```
scripts/query_bus.py    查询脚本（Agent 调用这个）
scripts/build_db.py     数据源 + 重建脚本
data/bus.db             SQLite 数据库
```

三张表：
- `routes` —— 线路，字段仅 `id, origin, destination, date, period, time_window, direction, promo, note, section, season, status`；**没有到达时刻字段**，`arrival` 由脚本用发车估算 + 车程推算
- `campus_alias` —— 高校统称 ↔ 真实校名 ↔ 学生口语，字段 `id, cluster, alias, alias_type, verified, note`
- `faq` —— 退改签、乘车、优惠等政策问答

> 数据库路径由脚本自动定位（相对脚本自身位置），**更换安装目录无需改任何代码**。

## 查询流程（严格按顺序）

### 第 1 步：归一地名

用户说的是「陶大」「江财」「景德镇陶瓷大学」还是「南昌工学院共青校区」，都要先映射到业务统称。

```bash
cd "<本 SKILL.md 所在目录>"; python scripts/query_bus.py --alias 陶大
```

> **Windows PowerShell 不支持 `&&`**，多条命令一律用 `;` 分隔（`cd ... ; python ...`）。
> `query_bus.py` 只接受 `--from X --to Y [--date D]` 参数形式，位置参数（`query_bus.py 宁都 景德镇`）会报 `unrecognized arguments`。

> `<本 SKILL.md 所在目录>` 就是读取本文件时拿到的路径所在目录（例如 `~/.nanobot/workspace/skills/zhi-tong-che` 或 `~/.workbuddy/skills/zhi-tong-che`）。
> 若平台已把该目录设为工作目录，可省略 `cd`。
> **不要先 `dir` / `ls` 探路**，路径在启动时已确定。
> 脚本已内置 UTF-8 输出处理，**不需要**再设 `PYTHONIOENCODING` 或 `chcp`。

返回 `"clusters": ["景德镇"]` 说明归属明确；返回多个统称说明**有歧义**。

### 第 2 步：查班次

```bash
python scripts/query_bus.py --from 景德镇 --to 宁都 --date 9-30
```

日期支持 `2026-09-30`、`9-30`、`0930`、`9月30日` 四种写法。
`--from` / `--to` 都支持传学生口语，脚本内部会归一。

只想知道某校能去哪：

```bash
python scripts/query_bus.py --from 景德镇
```

只想知道某县能从哪些学校出发：

```bash
python scripts/query_bus.py --to 宁都 --date 10-1
```

查政策类问题：

```bash
python scripts/query_bus.py --faq 优惠
```

### 第 3 步：读返回值

关键字段：

| 字段 | 含义 | 怎么用 |
|---|---|---|
| `found` / `count` | 有没有、几条 | `false` 就按「无班次」处理 |
| `routes[]` | 命中的班次 | 直接引用，别改写时间 |
| `routes[].status` | `planned` 已排班 / `confirmed` 已确认开通 / `suspended` 本期停运 | **决定话术强度，见规则 8** |
| `ambiguity[]` | 名称歧义 | **非空就必须追问，不能继续** |
| `hints[]` | 替代方案 | 查不到时用它给建议 |
| `resolved` | 归一后的实际查询值 | 核对是否理解正确 |
| `duration` | 车程（已按惯例 +30 分钟缓冲） | 直接引用 `text`，见规则 9 |
| `notice` | 兜底声明 | **必须转述给学生**，不能略过 |

## 回答规则（硬性约束）

1. **不许编造班次。** `found=false` 时直接说"当前没有查到这条线路"，再用 `hints` 给替代日期或让用户联系客服。绝不"估计大概有"。

2. **有歧义必须追问。** `ambiguity` 非空时，先问清楚是哪所学校/哪个校区，问清之前不给任何班次结论。
   例："江西洪州职业学院"同时属丰城和宜春两个统称，必须问"你是丰城校区还是宜春校区？"

3. **日期必须明确。** 用户说"国庆""放假那天"，要追问具体日期。库里只有 9-30 / 10-1 / 10-6 / 10-7 四天。

4. **优惠只在匹配时提。** 只有 `routes[].promo` 有值才说优惠，不要主动给别的线路套优惠。
   现有优惠仅两条：上饶→赣县/赣州/南康 满减 40；抚州→兴国 优惠 60。

5. **待确认项直说不知道。** FAQ 里标着"待补充"的（退票规则、上车点、行李额度），回答"这个需要联系客服确认"，不要自己补。

6. **区分方向。** `direction=out` 是返乡（高校→县域），`back` 是返校（县域→高校）。用户问"回学校"就是查 back，别给返乡班次。

7. **对学生别用内部术语。** 不要跟学生说"返乡方向""返校方向""反方向"，用他的语境说「你从学校回家」还是「你从家回学校」。术语只用于你自己判断方向。

8. **绝不承诺有票（最重要）。** 数据库是**排班计划**，不是**库存**。学生能不能走，只有小程序实时售票页说了算。
   - `status=planned` → 说「排了班次」，但必须补「实际是否开通、有没有票，请在小程序确认」
   - `status=confirmed` → 说「这条线路已确认开通」，**仍然**要补「余票以小程序为准」
   - `status=suspended` → 明确说「这条线路本期没有开」，不要含糊
   - **任何情况下都不许说「有票」「可以坐」「一定能走」「放心买」**
   - 返回值里的 `notice` 字段是脚本给你的兜底话术，**必须转述**，不能省略

   学生白跑一趟的成本，远高于多打一行字。

9. **车程只说预计，不打包票。**
   - `duration.text` 已经是「导航耗时 + 30 分钟缓冲」的结果，**直接用它**，不要自己换算
   - `duration.basis` 可以用来向学生解释依据（"导航 2 小时 40 分，我们一般加半小时"）
   - 说「车程约 3 小时 10 分」，**不要**说「3 小时能到」「准时 3 小时」
   - **没有 `duration` 字段时，先用同一条命令加 `--live` 重查一次**——它会实时调高德补算并写回缓存。只有 `--live` 也拿不到，才回答「具体车程要看当天路况」，**禁止自己估算数字**
   - 「`duration.source`」为 `amap_live` 说明是刚实时算的，`amap` 是预计算缓存，`manual` 是人工录入，回答时无需向学生解释来源差异

10. **发车时间一律加「左右」。** `depart_estimate` 是估算的代表时刻，不是精确时刻。
   - 有时段的取中间值（12:00-14:00 → 13:00），无时段的按时间段兜底（早上→09:00、中午→12:30）
   - 说「中午 1 点左右发车」「早上 9 点左右」，**不要说「13:00 发车」「9 点整」**
   - `depart_note` 说明了估算依据，被追问时可以解释，但不必主动展开
   - 同一时段内可能有多班车滚动发车，所以「左右」不是含糊，是准确
   - **凡是回答了发车时间，就必须补 `depart_disclaimer` 那句话**：「小程序下单出票后，小程序上会显示具体的上车时间（出票一般在出发前一天）」
   - 这句不是免责声明，是给学生一个确定的下一步——**让"估算"变成"下单后就准"**

11. **到达时间 = 发车 + 导航 + 30 分车程缓冲 + 30 分服务区休息。**
   - 脚本已经算好在 `routes[].arrival` 里，**直接引用，不要自己加**
   - **必须原样引用 `arrival` 和 `depart_estimate` 的数值，禁止四舍五入、禁止自己换算**。`13:13` 就说「下午 1 点 13 分左右」，不能改口成「1 点 10 分」
   - 说「大约下午 4 点 40 到」，**不要说「16:40 准时到」**
   - 值形如 `次日 01:30` 说明跨天，必须说「**次日凌晨** 1 点半左右」，不能只说「1:30」，否则学生会以为是当天中午
   - **凡是回答车程或到达时间，必须补 `rest_notice` 那句**：「一般中途会在服务区休息 30 分钟」。学生不知道车会停，就会把到达时间算早
   - 到达时间同样受规则 10 的出票话术覆盖：出票后小程序上会有准确信息

## 学生常见问法对照

| 学生会说 | 实际含义 |
|---|---|
| "30号中午有车吗" | date=9-30, period=中午（12:00-14:00） |
| "陶大能到宁都吧" | 景德镇 → 宁都 |
| "两人一起便宜吗" | 查 promo 字段 |
| "6号回学校" | direction=back, date=10-6 |
| "筠门岭" | 寻乌筠门岭（独立目的地，不等于寻乌） |
| "景德镇艺术职业大学" | 属景德镇统称（campus_alias id=71，verified，无歧义） |
| "江西艺术职业学院" | 属南昌统称（id=42），勿与景德镇艺术职业大学混淆 |

## 维护

### 核对实际开通状态（重要）

数据表是**排班计划**，小程序上能不能买要人工核对。核对完用这个脚本记下来：

```bash
# 看哪些还没核对
python scripts/mark_status.py --list --status planned

# 确认某条线路可买
python scripts/mark_status.py --set confirmed --from 景德镇 --to 宁都 --date 9-30

# 某个日期批次全部核对过了
python scripts/mark_status.py --set confirmed --date 9-30 --yes

# 本期停运
python scripts/mark_status.py --set suspended --from 鹰潭 --to 兴国 --date 10-1
```

状态变化后，Agent 的话术会自动跟着变（见规则 8）。

### 录车程

导航软件上查到的耗时，按分钟录进去，脚本会自动加 30 分钟缓冲：

```bash
# 导航显示 2 小时 40 分 → 160
python scripts/set_duration.py --from 景德镇 --to 宁都 --minutes 160

# 批量从 CSV 导入（origin,destination,minutes，无表头）
python scripts/set_duration.py --import durations.csv

# 看已录的
python scripts/set_duration.py --list
```

> 库里存的是**导航原始时间**，加 30 分钟是展示层规则（`query_bus.py` 里的 `BUFFER_MINUTES`）。
> 哪天改成加 40 分钟，改那一个常量即可，**不用重录**。

### 批量补车程（高德接口）

有高德 Web 服务 Key 时，可以一次把没录的线路全算出来：

```bash
python scripts/build_geo.py --key 你的Key            # 全量
python scripts/build_geo.py --key 你的Key --limit 5  # 先试 5 条
python scripts/build_geo.py --dry-run                # 只看要调多少次
```

规则：
- **不覆盖人工录入的记录**（`source='manual'`），你的经验比接口准
- 地名按城市级坐标近似（"景德镇"取景德镇市坐标），对几小时车程的误差可忽略
- 全程约 270 次调用，个人 Key 免费额度够用
- 算完仍然是导航原始值，对外答复照样 +30 分钟

### 改线路数据

编辑 `scripts/build_db.py` 里的 `ROUTES`，然后重跑

```bash
python scripts/build_db.py
```

新增学生口语别名：编辑 `ALIASES`，口语条目 `verified` 填 0 表示待确认。

寒假新期次：把 `SEASON` 改成「2027寒假」，照同样结构加数据，`season` 字段会区分开。

## 移植到其他 Agent 平台

本技能依赖两样东西：**SKILL.md 说明书** + **可执行的 Python 脚本**。

| 平台 | 直接用？ | 说明 |
|---|---|---|
| nanobot / OpenClaw | ✅ | 原始格式，放 `~/.nanobot/workspace/skills/` |
| WorkBuddy | ✅ | 同款 frontmatter，放 `~/.workbuddy/skills/` |
| Claude Code | ✅ | Anthropic Agent Skills 同源格式 |
| Dify / MaxKB | ⚠️ | 需把 `query_bus.py` 包成外部工具/代码节点，SKILL.md 转成提示词 |
| Coze / 扣子 | ⚠️ | 需转成插件 + 工作流，格式不兼容 |
| 豆包 App / 纯对话产品 | ❌ | 无法执行脚本，只能当知识库文本，会退化成"纯 RAG 编造班次" |

**关键：换平台时真正要搬的是 `scripts/` 和 `data/`，SKILL.md 只是说明书。**
目标平台如果没有命令执行能力，这套精确查询就失效了。

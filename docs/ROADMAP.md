下面给出一条可落地的技术实现路径，覆盖三种系统形态（提示系统 / 半自动 / 全自动）。默认你用 IBKR（你之前提到过），语言用 Python（生态最完整），数据用 1s/1m K 线与盘口快照。

---

## 0) 总体架构（所有形态通用）

核心模块永远是这 6 个，区别只是“谁来点确认键”：

1. **Market Data**：订阅行情（tick / 1s bar / 1m bar）、VWAP、盘口
2. **Signal Engine**：根据规则产出信号（入场/出场/不交易）
3. **Risk Engine**：仓位、止损止盈、最大回撤、交易次数限制
4. **Execution Engine**：下单、改单、撤单、成交回报处理
5. **State Store**：保存当日状态（是否已交易、当前R、持仓、订单）
6. **Logging & Replay**：记录每一步，方便复盘与回测一致性

你的系统要做成“状态机”，而不是一堆 if。

---

## 1) Phase A：提示系统（信号输出，不自动下单）

### 目标

把你现在的“看盘判断”变成**一致的、可复现的提示**，但把执行留给手动点击。

### 你需要实现的功能

**A. 数据层**

* 订阅 QQQM / AAPL：

  * 最新价
  * 1m bar（至少 OHLCV）
  * 当日累计成交量
* 计算指标：

  * 当日 VWAP（用 tick 或 1m 近似）
  * Opening Range（OR5/OR15）
  * 日线 20MA（可提前算好存本地）

**B. 信号层（只做输出）**
输出 4 类信息：

* 今日类型：趋势 / 震荡 / 事件（规则化）
* 可交易窗口：9:45–11:00，13:30–15:30
* 入场条件是否满足（VWAP 回踩+收回等）
* 风控建议（止损价、目标价、最大仓位）

**C. 展示层**

* 命令行输出也够用
* 或简单 web UI（FastAPI + 简单前端）
* 或直接发到 Telegram/Discord/Slack（你看得见即可）

### 关键点

提示系统最重要的是：**把“今天不交易”也输出为一个确定结论**。

---

## 2) Phase B：半自动系统（自动下单+风控，人工“总开关”）

这是最推荐的形态：你保留“是否允许交易”的最终决定权，其余全部自动化。

### 目标

* 你只做两件事：

  1. 开盘后 9:45 允许/禁止交易
  2. 在出现信号时确认“执行/跳过”（可选）

### 技术实现拆解

**A. 执行引擎（Execution Engine）**
必须支持：

* Place order：限价/市价/止损
* Modify order：移动止损、追踪止盈
* Cancel order
* Fill handling：部分成交、滑点记录、成交回报

IBKR 上通常用：

* `ib_insync`（Python 更顺滑）
* 或官方 TWS API

**B. 风控引擎（Risk Engine）**
必须硬编码以下“锁”：

* 当日最大亏损（例如 -1R 或 -2R）触发后：禁止新开仓，只允许平仓
* 每日最多 N 笔（建议 1–2 笔）
* 单笔最大仓位（例如 2%–4% 总资产的 T 资金池）
* 不允许在事件窗口交易（例如 FOMC 前后 30–60 分钟）

风控引擎要优先级最高：信号再强也不能越过风控。

**C. 状态机（State Machine）**
建议定义状态：

* `PREMARKET`
* `OPENING_NO_TRADE`（9:30–9:45）
* `TRADING_ALLOWED`
* `IN_POSITION`
* `COOLDOWN`（刚止损/刚止盈，冷静期）
* `LOCKED`（触发日内最大亏损）
* `DONE`（收盘前强制平仓/停止）

所有模块只通过状态机通信，防止逻辑互相覆盖。

**D. 交易逻辑（你的VWAP体系可机械化）**
典型入场（多头）：

* 价格 > VWAP
* 回踩到 VWAP 附近（用ATR或标准差定义“附近”）
* 重新站回 VWAP 且形成确认K线
* 下限价单
  止损：
* 回踩低点下方或 VWAP 下方固定距离
  止盈：
* 1R 先出一半，剩余用移动止损

**E. 人工开关的实现方式**

* 本地按键/命令：输入 `ALLOW=1`
* 或 UI 按钮
* 或定时策略：默认禁止，手动开启

---

## 3) Phase C：全自动系统（无人值守）

全自动不是“多写点代码”，而是需要更强的工程保障。

### 你必须额外实现

**A. 故障与异常处理**

* 断线重连（行情与交易通道）
* 订单状态一致性校验（系统状态 vs 券商真实状态）
* 幂等性：重复下单不会导致多开仓
* 熔断：异常波动/异常成交量/异常滑点自动暂停

**B. 交易前日历过滤**

* 事件日（FOMC、CPI、非农、公司财报）自动禁用或降低仓位
* 你可以用公开日历拉取，或手动维护一份 JSON 日历

**C. 更严格的执行优化**

* 限价优先，避免滑点吞噬
* 盘口检查：价差过大禁止入场
* 成交量不足禁止入场

**D. 监控与告警**

* 实时监控进程（systemd / supervisor）
* 告警（短信/Telegram）
* 每日自动生成交易报告（PnL、R、执行偏差）

### 全自动的底线

任何时候出现以下情况必须自动转入 `SAFE_MODE`：

* 行情断联超过 X 秒
* 下单未确认超过 X 秒
* 发现持仓与本地状态不一致
* 当日亏损触发阈值

---

## 4) 回测与实盘一致性的关键（否则必死）

日内策略最常见的失败点：回测用的是“完美成交”，实盘是“现实摩擦”。

你需要：

* **用 1min 数据做逻辑验证**（结构是否有优势）
* **用 tick/1s 数据做执行验证**（滑点/成交可行性）
* 回测中显式加入：

  * 价差成本
  * 手续费
  * 延迟（下单到成交的时间）

并且把同一套“Signal + Risk”代码复用到实盘，避免两套逻辑漂移。

---

## 5) 你现在的最短可行路径（MVP）

按最少工作量、最大确定性排序：

1. **提示系统（1–2 周）**

   * 能每天固定输出：今日类型、交易许可、入场/止损价
2. **半自动（2–4 周）**

   * 自动下单 + 自动止损止盈 + 日内锁仓
3. **全自动（再往后）**

   * 加日历、熔断、监控、告警、断线自愈

---

## 6) 你需要做的工程选择（不问你问题，直接给默认）

* 语言：Python
* IBKR 接口：`ib_insync`
* 数据缓存：SQLite（够用）
* 日志：CSV + JSON（每笔交易一条完整记录）
* 部署：一台本地电脑跑（半自动），全自动再上 VPS


一、第一阶段（提示系统）的技术栈清单
1) 运行环境

Python 3.11+

包管理：uv 或 poetry（二选一；uv更轻）

虚拟环境：venv（由 uv/poetry 管）

2) 券商与行情

（以 IBKR 为主）

连接与下单接口：ib_insync（封装 TWS/IB Gateway API）

IBKR 端：IB Gateway（优先）或 TWS

第一阶段只需要行情，不需要下单权限。

3) 数据处理与指标

数据框架：pandas

数值计算：numpy

时间处理：pendulum 或 Python 原生 datetime（建议 pendulum）

技术指标：自己实现（VWAP/OR），不依赖 TA-Lib（减少环境复杂度）

4) 存储（可选但强烈建议）

本地存储：SQLite

ORM：可不用；用标准库 sqlite3 够

用途：

记录每分钟数据/指标快照

记录每日分类结果与触发原因（可复盘）

5) 输出与通知

第一阶段选一个输出通道即可：

终端输出：rich（可选）

写 Markdown：直接写文件（Obsidian可读）

通知：Telegram Bot / Discord Webhook（二选一）

6) 开发质量（建议）

格式化：ruff（含 lint + format）

类型：mypy（可选）

日志：loguru 或标准 logging

二、项目目录结构（第一阶段推荐模板）
tbot/
  README.md
  pyproject.toml
  .env.example
  .gitignore

  data/
    raw/                  # 原始行情缓存（可选）
    db/                   # sqlite 文件
    reports/              # 每日输出（md/json）

  config/
    symbols.yaml          # 标的列表：QQQM, AAPL, MU
    params.yaml           # 参数：OR窗口、阈值、时间窗口等
    calendar.yaml         # 事件日/禁交易日（先手动维护）

  src/
    tbot/
      __init__.py

      main.py             # 程序入口：跑一整天或跑一次快照
      settings.py         # 读取 env/config，生成 Settings 对象

      brokers/
        __init__.py
        ibkr_client.py    # 连接 IB Gateway/TWS，订阅行情，拉取bars

      datafeed/
        __init__.py
        bar_aggregator.py # tick -> 1s/1m bar（若直接订阅1m可省略）
        store.py          # sqlite 写入/读取

      indicators/
        __init__.py
        vwap.py           # VWAP 计算（session-based）
        opening_range.py  # OR5/OR15
        ma20.py           # 日线20MA（可从历史bars算）

      regime/
        __init__.py
        rules.py          # 规则分类：趋势日/震荡日/事件日
        features.py       # 生成用于分类的特征（OHLCV, VWAP偏离等）

      report/
        __init__.py
        daily_report.py   # 生成Markdown/JSON报告（Obsidian友好）
        notifier.py       # Telegram/Discord（可选）

      utils/
        __init__.py
        time.py           # 交易时段、时区、session边界
        logging.py        # 日志配置
        math.py           # 常用计算：zscore/atr等

  tests/
    test_vwap.py
    test_regime_rules.py
    test_opening_range.py

三、第一阶段的运行模式（你应该实现的两个命令）
1) 盘中实时（每分钟更新一次）

订阅 1m bars

更新 VWAP、OR、特征

输出：当前“日类型 + 证据 + 今日可交易窗口建议”

2) 收盘后总结（生成当日报告）

输出最终分类

输出关键统计：VWAP穿越次数、OR突破次数、趋势延续度等


1) 回测对象拆成三层
A. 分类器回测（Regime backtest）

衡量：趋势/震荡/事件的判别质量与稳定性。

B. 信号回测（Signal backtest）

在已知日类型下，验证 VWAP/OR 触发规则的质量（不含执行摩擦时的理论边际）。

C. 执行回测（Execution backtest）

加上滑点、价差、延迟、成交概率，验证在现实摩擦下是否还成立。

第一阶段至少做 A + B，C 可以先用粗糙模型近似。

2) 数据准备（必须一致）
数据粒度

最少：1分钟 bars（OHLCV）

更好：1秒 bars 或 tick（用于更真实 VWAP 和滑点）

数据范围

单标的：至少 200 个交易日（约 1 年）

你的标的：QQQM、AAPL、MU（NBIS 数据可能短、结构会偏差）

关键：交易时段统一

只用正规交易时段（RTH）9:30–16:00 ET

开盘前后边界要严格

3) A 层：分类器回测怎么做（不需要收益）
3.1 先做“自洽性回测”

你还没有人工标注标签时，用三步：

把你的规则分类器跑一遍：每天输出（trend/range/event）+ 证据（VWAP穿越次数、VWAP同侧占比等）

稳定性检查：

阈值微调 ±10% 时，分类变化是否剧烈？

同一标的不同年份是否统计分布一致？

可解释性检查：

每个分类都能被“证据字段”解释，而不是黑箱结果

输出指标（每天一条记录）：

regime

vwap_cross_count

pct_time_above_vwap

or_width

intraday_range / ATR20

early_volume_ratio (9:30–10:30 volume / full day)

3.2 如果你愿意人工标注（更可靠）

随机抽 50–100 天，把分钟图按定义人工打标签。
然后用：

Accuracy（总体）

Precision/Recall（趋势日的精确率更重要）

Confusion matrix（最重要）

你关心的是：

把震荡日误判成趋势日（最伤）

把趋势日误判成震荡日（损失机会但不致命）

4) B 层：信号回测怎么做（用“伪执行”）

第一阶段提示系统通常输出：

入场条件触发点

建议止损/止盈

建议仓位

回测要把它变成一个“可计算的交易事件”。

4.1 定义一个最简交易规则（必须完全机械）

示例（多头）：

时间窗口：9:45–11:00

条件：

价格在 VWAP 上方

回踩到 VWAP ± band（band = 0.1% 或 0.2% 或 ATR分位）

下一根 1m 收盘重新站上 VWAP

入场价：下一根 1m 开盘价（保守）

止损：回踩低点下方 X（或 VWAP 下方固定距离）

止盈：1R 出一半，剩余移动止损到 breakeven

每日最多 1 次

你要回测的是：这套提示规则在不同日类型下的统计表现。

4.2 输出指标（不要只看总收益）

按日类型分组输出：

win rate

avg R

median R

max loss（单笔）

expectancy（期望收益，以 R 衡量）

trade frequency（触发率）

你会得到类似结论：

Trend day：期望 > 0

Range day：期望 ≈ 0 或 < 0（那就应该禁做）
这才是“提示系统”的价值。

5) C 层：执行摩擦怎么建模（第一阶段用粗模就够）

即便只用 1m 数据，也要把摩擦加进去，否则全是幻觉。

最低限度加入三项：

手续费：按券商费率

价差成本：每次交易扣一个固定bps（如 1–3bps）或用历史平均bid-ask

滑点：每次成交扣固定bps（如 1–5bps），或按当日波动率动态调整

可加“延迟”：

信号触发后 N 秒才成交 → 用下一根 bar 的开盘/均价近似

6) 走样与数据泄漏（回测最常见坑）

必须避免：

用当天收盘后的信息去判断当天是趋势日（然后再回测当天早盘信号）
解决：分类要分成两种：

实时分类（只用到当前时刻数据）

收盘分类（用于统计研究）
实盘用实时分类，回测必须模拟“只看到当时数据”。

正确做法：

在回测中逐分钟推进时间 t

在 t 时刻只用 t 之前的数据计算 VWAP、OR、分类与信号

决策与下单都发生在 t 或 t+1

7) 回测输出应该长什么样（你要的产物）

至少生成三份文件：

regime_daily.csv

date, symbol, regime, evidence metrics...

trades.csv

date, symbol, regime_at_entry, entry_time, entry_price, exit_time, exit_price, R, notes

summary_by_regime.csv

regime, n_trades, win_rate, avg_R, median_R, max_dd_R, expectancy

另外生成一个 Obsidian 可读的 Markdown 日报/周报也很有用。

8) 推荐的最小回测流程（你现在就能做）

拉取 QQQM/AAPL/MU 最近 1–2 年的 1m 数据（RTH）

实现 VWAP、OR、实时分类器（每分钟更新）

实现一个唯一的、固定的入场规则（如 VWAP回踩收回）

加入摩擦（固定bps）

按日类型输出统计表，看“哪些日子应该禁做”



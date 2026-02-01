# T-Trade

日内交易提示系统，支持 IBKR TWS 连接与 Web 仪表盘。

## 功能

- 实时行情订阅与指标计算 (VWAP, Opening Range, MA20)
- 日类型分类 (趋势/震荡/事件)
- 交易时段与风控管理
- Web 仪表盘 (React + FastAPI)
- Watchlist 管理

## 当前状态

### Phase A - Web 仪表盘 (已完成)

- [x] FastAPI 后端 API
- [x] React 前端仪表盘
- [x] Watchlist 增删管理
- [x] Yahoo Finance 数据源集成
- [x] 股票状态卡片 (价格/VWAP/OR/日类型)
- [x] TWS 连接状态管理
- [x] 数据源切换 UI (Yahoo/TWS)

注: 由于 ib_insync 事件循环限制，当前 TWS 模式仅显示连接状态，实际数据统一来自 Yahoo Finance。

## 数据源

| 数据                | 来源          | 说明                 |
| ------------------- | ------------- | -------------------- |
| Dashboard 股票报价  | Yahoo Finance | Web 仪表盘主数据源   |
| 股票验证            | Yahoo Finance | 验证股票代码是否有效 |
| 实时行情 (tick/bar) | IBKR TWS      | CLI 模式使用         |
| VWAP/OR 指标        | IBKR TWS      | 基于实时行情计算     |
| 日线历史数据        | IBKR TWS      | 用于 MA20 等日线指标 |

## 快速开始

```bash
# 安装依赖
uv sync

# 启动 Web 仪表盘后端
uv run uvicorn tbot.api.main:app --port 8000

# 启动前端 (新终端)
cd frontend && npm install && npm run dev

# 访问 http://localhost:5173

# CLI 模式 - 演示 (无需 IBKR)
uv run tbot demo

# CLI 模式 - 连接 TWS
uv run tbot run --port 7497
```

## 配置

编辑 `config/params.yaml` 设置交易参数，`config/symbols.yaml` 设置监控标的。

TWS 连接参数:

- 端口 7497: TWS 纸盘
- 端口 7496: TWS 实盘
- 端口 4001: IB Gateway 实盘
- 端口 4002: IB Gateway 纸盘

## 项目结构

```
src/tbot/
  api/          # FastAPI 后端
  brokers/      # IBKR 客户端
  datafeed/     # 数据聚合与存储
  indicators/   # 技术指标
  regime/       # 日类型分类
frontend/       # React 仪表盘
config/         # 配置文件
docs/           # 项目文档
```

## 开发路线

### Phase B - TWS 实时数据服务 (计划中)

- [ ] TWSDataService 后台线程
- [ ] 持久化 TWS 连接管理
- [ ] 实时行情订阅与缓存
- [ ] API 从缓存读取 TWS 数据

### Phase C - 指标与策略增强

- [ ] 真实 VWAP 计算 (基于分钟数据)
- [ ] Opening Range 自动检测
- [ ] 更多技术指标
- [ ] 策略信号生成

### Phase D - 交易执行

- [ ] 订单管理
- [ ] 仓位跟踪
- [ ] 风控规则执行
- [ ] 交易日志与报告

## 文档

详细技术路线见 [docs/ROADMAP.md](docs/ROADMAP.md)

// API 类型定义

export interface MarketStatus {
  session: string;
  progress: number;
  trading_allowed: boolean;
  trading_reason: string;
  current_time: string;
}

export interface StockStatus {
  symbol: string;
  name: string;  // 股票名称
  exchange: string | null;  // 交易所
  price: number;
  vwap: number;
  vwap_diff_pct: number;
  above_vwap: boolean;
  or5_high: number | null;
  or5_low: number | null;
  or15_high: number | null;
  or15_low: number | null;
  or15_complete: boolean;
  regime: string;
  regime_confidence: number;
  regime_reasons: string[];
  updated_at: string;
}

export interface DashboardData {
  market_status: MarketStatus;
  watchlist: string[];
  stocks: StockStatus[];
  data_source: string;  // yahoo 或 tws
}

export interface WatchlistResponse {
  symbols: string[];
}

export interface DataSourceStatus {
  current: string;  // yahoo 或 tws
  tws_available: boolean;
  tws_error: string | null;
}

// API 请求模块

import { DashboardData, WatchlistResponse, StockStatus, MarketStatus } from './types';

const API_BASE = '/api';

export interface ValidateSymbolResponse {
  valid: boolean;
  symbol: string;
  name?: string;
  error?: string;
}

export async function fetchDashboard(): Promise<DashboardData> {
  const response = await fetch(`${API_BASE}/dashboard`);
  if (!response.ok) {
    throw new Error('Failed to fetch dashboard');
  }
  return response.json();
}

export async function fetchWatchlist(): Promise<WatchlistResponse> {
  const response = await fetch(`${API_BASE}/watchlist`);
  if (!response.ok) {
    throw new Error('Failed to fetch watchlist');
  }
  return response.json();
}

export async function addToWatchlist(symbol: string): Promise<WatchlistResponse> {
  const response = await fetch(`${API_BASE}/watchlist`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ symbol }),
  });
  if (!response.ok) {
    throw new Error('Failed to add to watchlist');
  }
  return response.json();
}

export async function removeFromWatchlist(symbol: string): Promise<WatchlistResponse> {
  const response = await fetch(`${API_BASE}/watchlist/${symbol}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error('Failed to remove from watchlist');
  }
  return response.json();
}

export async function fetchMarketStatus(): Promise<MarketStatus> {
  const response = await fetch(`${API_BASE}/market/status`);
  if (!response.ok) {
    throw new Error('Failed to fetch market status');
  }
  return response.json();
}

export async function fetchStockStatus(symbol: string): Promise<StockStatus> {
  const response = await fetch(`${API_BASE}/stocks/${symbol}`);
  if (!response.ok) {
    throw new Error('Failed to fetch stock status');
  }
  return response.json();
}

export async function validateSymbol(symbol: string): Promise<ValidateSymbolResponse> {
  const response = await fetch(`${API_BASE}/validate/${symbol}`);
  if (!response.ok) {
    return { valid: false, symbol, error: 'Failed to validate symbol' };
  }
  return response.json();
}

export async function addToWatchlistWithValidation(symbol: string): Promise<{ success: boolean; data?: WatchlistResponse; error?: string }> {
  // 先验证股票代码
  const validation = await validateSymbol(symbol);
  if (!validation.valid) {
    return { success: false, error: validation.error || `无效的股票代码: ${symbol}` };
  }
  
  // 验证通过，添加到 watchlist
  const response = await fetch(`${API_BASE}/watchlist`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ symbol: validation.symbol }),
  });
  
  if (!response.ok) {
    return { success: false, error: 'Failed to add to watchlist' };
  }
  
  return { success: true, data: await response.json() };
}

// Data Source API
export interface DataSourceStatus {
  current: string;
  tws_available: boolean;
  tws_error: string | null;
}

export async function getDataSource(): Promise<DataSourceStatus> {
  const response = await fetch(`${API_BASE}/datasource`);
  if (!response.ok) {
    throw new Error('Failed to get data source');
  }
  return response.json();
}

export async function setDataSource(source: string): Promise<DataSourceStatus> {
  const response = await fetch(`${API_BASE}/datasource`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ source }),
  });
  if (!response.ok) {
    throw new Error('Failed to set data source');
  }
  return response.json();
}

export async function connectTws(port: number = 7497): Promise<{ success: boolean; message: string; data_source: string }> {
  const response = await fetch(`${API_BASE}/datasource/connect-tws?port=${port}`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to connect to TWS');
  }
  return response.json();
}

import { useState, useEffect, useCallback } from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Activity, 
  AlertTriangle,
  Plus,
  X,
  RefreshCw,
  Clock,
  CheckCircle,
  XCircle,
  Database,
  Wifi,
  WifiOff,
  Globe,
  Calendar
} from 'lucide-react';
import { DashboardData, StockStatus, DataSourceStatus } from './types';
import { fetchDashboard, addToWatchlistWithValidation, removeFromWatchlist, getDataSource, setDataSource } from './api';

// ============== 时区类型 ==============

type TimezoneOption = 'ET' | 'LOCAL' | 'UTC';

const TIMEZONE_LABELS: Record<TimezoneOption, string> = {
  'ET': '美东时间',
  'LOCAL': '本地时间',
  'UTC': 'UTC',
};

/**
 * 将美东时间字符串转换为指定时区
 * @param etTimeStr 格式如 "2026-02-01 10:30:00 ET" 或 "10:30:00"
 * @param targetTz 目标时区
 * @returns 转换后的时间字符串
 */
function convertTimezone(etTimeStr: string, targetTz: TimezoneOption): string {
  if (targetTz === 'ET') return etTimeStr;
  
  try {
    // 解析 ET 时间
    let dateStr: string;
    let timeStr: string;
    
    if (etTimeStr.includes(' ET')) {
      // 格式: "2026-02-01 10:30:00 ET"
      const cleaned = etTimeStr.replace(' ET', '');
      const parts = cleaned.split(' ');
      dateStr = parts[0];
      timeStr = parts[1];
    } else if (etTimeStr.match(/^\d{2}:\d{2}:\d{2}$/)) {
      // 格式: "10:30:00" (只有时间)
      const today = new Date();
      dateStr = today.toISOString().split('T')[0];
      timeStr = etTimeStr;
    } else {
      return etTimeStr;
    }
    
    // 创建 ET 时间的 Date 对象
    // 美东时间 (EST: UTC-5, EDT: UTC-4)
    // 简化处理：假设使用 EST (UTC-5)
    const etDate = new Date(`${dateStr}T${timeStr}-05:00`);
    
    if (isNaN(etDate.getTime())) return etTimeStr;
    
    if (targetTz === 'UTC') {
      const hours = etDate.getUTCHours().toString().padStart(2, '0');
      const mins = etDate.getUTCMinutes().toString().padStart(2, '0');
      const secs = etDate.getUTCSeconds().toString().padStart(2, '0');
      return `${dateStr} ${hours}:${mins}:${secs} UTC`;
    } else if (targetTz === 'LOCAL') {
      const hours = etDate.getHours().toString().padStart(2, '0');
      const mins = etDate.getMinutes().toString().padStart(2, '0');
      const secs = etDate.getSeconds().toString().padStart(2, '0');
      // 获取本地时区偏移
      const offset = -etDate.getTimezoneOffset();
      const offsetHours = Math.floor(Math.abs(offset) / 60);
      const offsetSign = offset >= 0 ? '+' : '-';
      const tzName = `GMT${offsetSign}${offsetHours}`;
      return `${dateStr} ${hours}:${mins}:${secs} ${tzName}`;
    }
  } catch {
    return etTimeStr;
  }
  
  return etTimeStr;
}

// ============== 市场休市检测 ==============

// 美股节假日 (按年份配置)
const US_MARKET_HOLIDAYS: Record<number, { date: string; name: string }[]> = {
  2025: [
    { date: '2025-01-01', name: '元旦' },
    { date: '2025-01-20', name: '马丁·路德·金纪念日' },
    { date: '2025-02-17', name: '总统日' },
    { date: '2025-04-18', name: '耶稣受难日' },
    { date: '2025-05-26', name: '阵亡将士纪念日' },
    { date: '2025-06-19', name: '六月节' },
    { date: '2025-07-04', name: '独立日' },
    { date: '2025-09-01', name: '劳动节' },
    { date: '2025-11-27', name: '感恩节' },
    { date: '2025-12-25', name: '圣诞节' },
  ],
  2026: [
    { date: '2026-01-01', name: '元旦' },
    { date: '2026-01-19', name: '马丁·路德·金纪念日' },
    { date: '2026-02-16', name: '总统日' },
    { date: '2026-04-03', name: '耶稣受难日' },
    { date: '2026-05-25', name: '阵亡将士纪念日' },
    { date: '2026-06-19', name: '六月节' },
    { date: '2026-07-03', name: '独立日(观察日)' },
    { date: '2026-09-07', name: '劳动节' },
    { date: '2026-11-26', name: '感恩节' },
    { date: '2026-12-25', name: '圣诞节' },
  ],
  2027: [
    { date: '2027-01-01', name: '元旦' },
    { date: '2027-01-18', name: '马丁·路德·金纪念日' },
    { date: '2027-02-15', name: '总统日' },
    { date: '2027-03-26', name: '耶稣受难日' },
    { date: '2027-05-31', name: '阵亡将士纪念日' },
    { date: '2027-06-18', name: '六月节(观察日)' },
    { date: '2027-07-05', name: '独立日(观察日)' },
    { date: '2027-09-06', name: '劳动节' },
    { date: '2027-11-25', name: '感恩节' },
    { date: '2027-12-24', name: '圣诞节(观察日)' },
  ],
};

interface MarketClosedInfo {
  isClosed: boolean;
  reason: string;
  type: 'weekend' | 'holiday' | 'none';
  nextOpenDate?: string;
}

/**
 * 检测市场是否因周末或节假日休市
 */
function checkMarketClosed(etTimeStr: string): MarketClosedInfo {
  try {
    // 解析 ET 时间
    let dateStr: string;
    
    if (etTimeStr.includes(' ET')) {
      dateStr = etTimeStr.replace(' ET', '').split(' ')[0];
    } else {
      // 使用当前日期
      const now = new Date();
      dateStr = now.toISOString().split('T')[0];
    }
    
    const date = new Date(dateStr + 'T12:00:00');
    const dayOfWeek = date.getDay(); // 0 = Sunday, 6 = Saturday
    const year = date.getFullYear();
    
    // 检查周末
    if (dayOfWeek === 0) {
      return {
        isClosed: true,
        reason: '周日休市',
        type: 'weekend',
        nextOpenDate: getNextTradingDay(dateStr),
      };
    }
    if (dayOfWeek === 6) {
      return {
        isClosed: true,
        reason: '周六休市',
        type: 'weekend',
        nextOpenDate: getNextTradingDay(dateStr),
      };
    }
    
    // 检查节假日
    const holidays = US_MARKET_HOLIDAYS[year] || [];
    const holiday = holidays.find(h => h.date === dateStr);
    if (holiday) {
      return {
        isClosed: true,
        reason: `${holiday.name} - 休市`,
        type: 'holiday',
        nextOpenDate: getNextTradingDay(dateStr),
      };
    }
    
    return { isClosed: false, reason: '', type: 'none' };
  } catch {
    return { isClosed: false, reason: '', type: 'none' };
  }
}

/**
 * 获取下一个交易日
 */
function getNextTradingDay(dateStr: string): string {
  const date = new Date(dateStr + 'T12:00:00');
  const year = date.getFullYear();
  const holidays = US_MARKET_HOLIDAYS[year] || [];
  const holidayDates = new Set(holidays.map(h => h.date));
  
  // 最多查找 10 天
  for (let i = 1; i <= 10; i++) {
    const nextDate = new Date(date);
    nextDate.setDate(nextDate.getDate() + i);
    const nextDateStr = nextDate.toISOString().split('T')[0];
    const nextDayOfWeek = nextDate.getDay();
    
    // 跳过周末
    if (nextDayOfWeek === 0 || nextDayOfWeek === 6) continue;
    
    // 检查下一年的节假日
    const nextYear = nextDate.getFullYear();
    const nextYearHolidays = US_MARKET_HOLIDAYS[nextYear] || [];
    const nextHolidayDates = new Set(nextYearHolidays.map(h => h.date));
    
    // 跳过节假日
    if (holidayDates.has(nextDateStr) || nextHolidayDates.has(nextDateStr)) continue;
    
    return nextDateStr;
  }
  
  return '';
}

/**
 * 格式化日期为友好显示
 */
function formatDateFriendly(dateStr: string): string {
  if (!dateStr) return '';
  const date = new Date(dateStr + 'T12:00:00');
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const weekday = weekdays[date.getDay()];
  return `${month}月${day}日 (${weekday})`;
}

// ============== 辅助函数 ==============

function getRegimeIcon(regime: string) {
  switch (regime) {
    case 'trend_up':
      return <TrendingUp className="w-5 h-5 text-green-500" />;
    case 'trend_down':
      return <TrendingDown className="w-5 h-5 text-red-500" />;
    case 'range':
      return <Activity className="w-5 h-5 text-yellow-500" />;
    case 'event':
      return <AlertTriangle className="w-5 h-5 text-orange-500" />;
    default:
      return <Activity className="w-5 h-5 text-gray-500" />;
  }
}

function getRegimeLabel(regime: string) {
  const labels: Record<string, string> = {
    'trend_up': '上涨趋势',
    'trend_down': '下跌趋势',
    'range': '震荡',
    'event': '事件日',
    'unknown': '未知',
  };
  return labels[regime] || regime;
}

function getRegimeColor(regime: string) {
  const colors: Record<string, string> = {
    'trend_up': 'bg-green-100 text-green-800 border-green-200',
    'trend_down': 'bg-red-100 text-red-800 border-red-200',
    'range': 'bg-yellow-100 text-yellow-800 border-yellow-200',
    'event': 'bg-orange-100 text-orange-800 border-orange-200',
    'unknown': 'bg-gray-100 text-gray-800 border-gray-200',
  };
  return colors[regime] || colors['unknown'];
}

function getSessionLabel(session: string) {
  const labels: Record<string, string> = {
    'premarket': '盘前',
    'opening': '开盘期',
    'morning': '上午交易',
    'midday': '午间',
    'afternoon': '下午交易',
    'close_only': '收盘前',
    'afterhours': '盘后',
    'closed': '休市',
  };
  return labels[session] || session;
}

// ============== 组件 ==============

/**
 * 获取交易时间（根据时区转换）
 */
function getMarketHours(timezone: TimezoneOption): { 
  premarket: string; 
  open: string; 
  close: string; 
  afterhours: string;
} {
  // 美股固定时间 (ET)
  const hours = {
    premarket: '04:00',
    open: '09:30',
    close: '16:00',
    afterhours: '20:00',
  };
  
  if (timezone === 'ET') {
    return {
      premarket: `${hours.premarket} ET`,
      open: `${hours.open} ET`,
      close: `${hours.close} ET`,
      afterhours: `${hours.afterhours} ET`,
    };
  }
  
  // 转换时间
  const today = new Date().toISOString().split('T')[0];
  const convertTime = (time: string) => {
    const result = convertTimezone(`${today} ${time}:00 ET`, timezone);
    // 只提取时间部分
    const match = result.match(/(\d{2}:\d{2})/);
    if (match) {
      const suffix = timezone === 'UTC' ? ' UTC' : '';
      return match[1] + suffix;
    }
    return time;
  };
  
  return {
    premarket: convertTime(hours.premarket),
    open: convertTime(hours.open),
    close: convertTime(hours.close),
    afterhours: convertTime(hours.afterhours),
  };
}

/**
 * 获取时段对应的时间范围
 */
function getSessionTimeRange(session: string, timezone: TimezoneOption): string {
  const hours = getMarketHours(timezone);
  
  const ranges: Record<string, string> = {
    'premarket': `${hours.premarket} - ${hours.open}`,
    'opening': `${hours.open} - 开盘后30分钟`,
    'morning': `${hours.open} - 12:00`,
    'midday': '12:00 - 13:00',
    'afternoon': `13:00 - ${hours.close}`,
    'close_only': `收盘前15分钟 - ${hours.close}`,
    'afterhours': `${hours.close} - ${hours.afterhours}`,
    'closed': '休市',
  };
  
  return ranges[session] || '';
}

function MarketStatusCard({ 
  session, 
  progress, 
  tradingAllowed, 
  tradingReason, 
  currentTime,
  timezone,
}: { 
  session: string;
  progress: number;
  tradingAllowed: boolean;
  tradingReason: string;
  currentTime: string;
  timezone: TimezoneOption;
}) {
  const displayTime = convertTimezone(currentTime, timezone);
  const marketHours = getMarketHours(timezone);
  const sessionTimeRange = getSessionTimeRange(session, timezone);
  const closedInfo = checkMarketClosed(currentTime);
  
  // 如果是周末或节假日休市，显示特殊界面
  if (closedInfo.isClosed) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">市场状态</h2>
          <div className="flex items-center text-gray-500 text-sm">
            <Clock className="w-4 h-4 mr-1" />
            {displayTime}
          </div>
        </div>
        
        <div className="bg-gray-100 rounded-lg p-6 text-center">
          <div className="flex justify-center mb-3">
            {closedInfo.type === 'weekend' ? (
              <Calendar className="w-12 h-12 text-gray-400" />
            ) : (
              <AlertTriangle className="w-12 h-12 text-orange-400" />
            )}
          </div>
          <div className="text-xl font-semibold text-gray-700 mb-2">
            {closedInfo.reason}
          </div>
          {closedInfo.nextOpenDate && (
            <div className="text-sm text-gray-500">
              下一交易日: <span className="font-medium text-blue-600">{formatDateFriendly(closedInfo.nextOpenDate)}</span>
              <span className="ml-2">({marketHours.open} 开盘)</span>
            </div>
          )}
        </div>
        
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-gray-500">
          <div className="bg-gray-50 rounded p-2 text-center">
            <div className="font-medium">盘前交易</div>
            <div>{marketHours.premarket}</div>
          </div>
          <div className="bg-gray-50 rounded p-2 text-center">
            <div className="font-medium">开盘</div>
            <div>{marketHours.open}</div>
          </div>
          <div className="bg-gray-50 rounded p-2 text-center">
            <div className="font-medium">收盘</div>
            <div>{marketHours.close}</div>
          </div>
          <div className="bg-gray-50 rounded p-2 text-center">
            <div className="font-medium">盘后交易</div>
            <div>至 {marketHours.afterhours}</div>
          </div>
        </div>
      </div>
    );
  }
  
  // 正常交易日界面
  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">市场状态</h2>
        <div className="flex items-center text-gray-500 text-sm">
          <Clock className="w-4 h-4 mr-1" />
          {displayTime}
        </div>
      </div>
      
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gray-50 rounded-lg p-4">
          <div className="text-sm text-gray-500 mb-1">时段</div>
          <div className="text-lg font-medium text-gray-800">{getSessionLabel(session)}</div>
          {sessionTimeRange && (
            <div className="text-xs text-gray-400 mt-1">{sessionTimeRange}</div>
          )}
        </div>
        
        <div className="bg-gray-50 rounded-lg p-4">
          <div className="text-sm text-gray-500 mb-1">交易进度</div>
          <div className="flex items-center">
            <div className="flex-1 bg-gray-200 rounded-full h-2 mr-2">
              <div 
                className="bg-blue-500 h-2 rounded-full" 
                style={{ width: `${progress * 100}%` }}
              />
            </div>
            <span className="text-sm font-medium text-gray-700">{(progress * 100).toFixed(0)}%</span>
          </div>
          <div className="text-xs text-gray-400 mt-1">
            开盘 {marketHours.open} → 收盘 {marketHours.close}
          </div>
        </div>
        
        <div className="bg-gray-50 rounded-lg p-4 col-span-2">
          <div className="text-sm text-gray-500 mb-1">交易许可</div>
          <div className="flex items-center">
            {tradingAllowed ? (
              <CheckCircle className="w-5 h-5 text-green-500 mr-2" />
            ) : (
              <XCircle className="w-5 h-5 text-red-500 mr-2" />
            )}
            <span className={`font-medium ${tradingAllowed ? 'text-green-700' : 'text-red-700'}`}>
              {tradingAllowed ? '允许交易' : '禁止交易'}
            </span>
            <span className="text-gray-500 text-sm ml-2">- {tradingReason}</span>
          </div>
          <div className="text-xs text-gray-400 mt-2 flex gap-4">
            <span>盘前: {marketHours.premarket}</span>
            <span>盘后: {marketHours.close} - {marketHours.afterhours}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * 迷你走势图组件
 */
function Sparkline({ 
  data, 
  width = 120, 
  height = 40,
  color,
}: { 
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (!data || data.length < 2) {
    return (
      <div 
        className="flex items-center justify-center text-gray-300 text-xs"
        style={{ width, height }}
      >
        暂无数据
      </div>
    );
  }
  
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  
  // 计算涨跌颜色
  const isUp = data[data.length - 1] >= data[0];
  const lineColor = color || (isUp ? '#22c55e' : '#ef4444'); // green-500 / red-500
  
  // 生成 SVG path
  const padding = 2;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;
  
  const points = data.map((value, index) => {
    const x = padding + (index / (data.length - 1)) * chartWidth;
    const y = padding + chartHeight - ((value - min) / range) * chartHeight;
    return `${x},${y}`;
  });
  
  const pathD = `M ${points.join(' L ')}`;
  
  // 创建渐变填充区域
  const areaPoints = [
    `${padding},${height - padding}`,
    ...points,
    `${width - padding},${height - padding}`,
  ];
  const areaD = `M ${areaPoints.join(' L ')} Z`;
  
  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={`gradient-${isUp ? 'up' : 'down'}`} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={lineColor} stopOpacity="0.3" />
          <stop offset="100%" stopColor={lineColor} stopOpacity="0.05" />
        </linearGradient>
      </defs>
      {/* 填充区域 */}
      <path
        d={areaD}
        fill={`url(#gradient-${isUp ? 'up' : 'down'})`}
      />
      {/* 折线 */}
      <path
        d={pathD}
        fill="none"
        stroke={lineColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* 当前价格点 */}
      <circle
        cx={width - padding}
        cy={padding + chartHeight - ((data[data.length - 1] - min) / range) * chartHeight}
        r="2.5"
        fill={lineColor}
      />
    </svg>
  );
}

function WatchlistInput({ 
  onAdd, 
  disabled 
}: { 
  onAdd: (symbol: string) => Promise<string | null>;
  disabled: boolean;
}) {
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || validating) return;
    
    setValidating(true);
    setError(null);
    
    const result = await onAdd(input.trim().toUpperCase());
    
    if (result) {
      setError(result);
    } else {
      setInput('');
    }
    setValidating(false);
  };
  
  return (
    <div>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => {
            setInput(e.target.value.toUpperCase());
            setError(null);
          }}
          placeholder="输入股票代码 (如 AAPL, MSFT)..."
          className={`flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent ${
            error ? 'border-red-300 bg-red-50' : 'border-gray-300'
          }`}
          disabled={disabled || validating}
          maxLength={10}
        />
        <button
          type="submit"
          disabled={disabled || !input.trim() || validating}
          className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
        >
          {validating ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <Plus className="w-4 h-4" />
          )}
          {validating ? '验证中...' : '添加'}
        </button>
      </form>
      {error && (
        <div className="mt-2 text-sm text-red-600 flex items-center gap-1">
          <XCircle className="w-4 h-4" />
          {error}
        </div>
      )}
    </div>
  );
}

function StockCard({ 
  stock, 
  onRemove,
  expanded,
  onToggleExpand,
}: { 
  stock: StockStatus;
  onRemove: (symbol: string) => void;
  expanded: boolean;
  onToggleExpand: () => void;
}) {
  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      {/* 头部 */}
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {getRegimeIcon(stock.regime)}
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-lg text-gray-800">{stock.symbol}</h3>
                {stock.exchange && (
                  <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded">
                    {stock.exchange}
                  </span>
                )}
              </div>
              <div className="text-sm text-gray-500 truncate max-w-[200px]" title={stock.name}>
                {stock.name !== stock.symbol ? stock.name : ''}
              </div>
              <span className={`text-xs px-2 py-0.5 rounded-full border ${getRegimeColor(stock.regime)}`}>
                {getRegimeLabel(stock.regime)}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* 迷你走势图 */}
            <div className="hidden sm:block">
              <Sparkline data={stock.sparkline || []} width={100} height={36} />
            </div>
            <button
              onClick={() => onRemove(stock.symbol)}
              className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded"
              title="从 Watchlist 移除"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
      
      {/* 今日走势图 (移动端显示) */}
      <div className="sm:hidden px-4 py-2 bg-gray-50 border-b border-gray-100 flex justify-center">
        <Sparkline data={stock.sparkline || []} width={200} height={40} />
      </div>
      
      {/* 价格信息 */}
      <div className="p-4 bg-gray-50">
        <div className="grid grid-cols-4 gap-3 text-center">
          <div>
            <div className="text-2xl font-bold text-gray-800">${stock.price.toFixed(2)}</div>
            <div className="text-xs text-gray-500">当前价格</div>
          </div>
          <div>
            <div className="text-xl font-semibold text-blue-600">${stock.vwap.toFixed(2)}</div>
            <div className="text-xs text-gray-500">VWAP</div>
          </div>
          <div>
            <div className={`text-xl font-semibold ${stock.above_vwap ? 'text-green-600' : 'text-red-600'}`}>
              {stock.vwap_diff_pct > 0 ? '+' : ''}{stock.vwap_diff_pct.toFixed(2)}%
            </div>
            <div className="text-xs text-gray-500">
              {stock.above_vwap ? 'VWAP上方' : 'VWAP下方'}
            </div>
          </div>
          <div>
            <div className="text-xl font-semibold text-purple-600">
              {stock.ma20 ? `$${stock.ma20.toFixed(2)}` : '-'}
            </div>
            <div className="text-xs text-gray-500">MA20</div>
          </div>
        </div>
        
        {/* 日内数据 */}
        <div className="grid grid-cols-4 gap-3 text-center mt-3 pt-3 border-t border-gray-200">
          <div>
            <div className="text-sm font-medium text-gray-700">
              {stock.day_open ? `$${stock.day_open.toFixed(2)}` : '-'}
            </div>
            <div className="text-xs text-gray-400">开盘</div>
          </div>
          <div>
            <div className="text-sm font-medium text-green-600">
              {stock.day_high ? `$${stock.day_high.toFixed(2)}` : '-'}
            </div>
            <div className="text-xs text-gray-400">最高</div>
          </div>
          <div>
            <div className="text-sm font-medium text-red-600">
              {stock.day_low ? `$${stock.day_low.toFixed(2)}` : '-'}
            </div>
            <div className="text-xs text-gray-400">最低</div>
          </div>
          <div>
            <div className="text-sm font-medium text-gray-700">
              {stock.prev_close ? `$${stock.prev_close.toFixed(2)}` : '-'}
            </div>
            <div className="text-xs text-gray-400">昨收</div>
          </div>
        </div>
      </div>
      
      {/* OR 信息 */}
      {stock.or15_complete && (
        <div className="p-4 border-t border-gray-100">
          <div className="text-sm text-gray-600 mb-2 font-medium">Opening Range (OR15)</div>
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-green-50 rounded p-2 text-center">
              <div className="text-green-700 font-semibold">${stock.or15_high?.toFixed(2)}</div>
              <div className="text-xs text-green-600">High</div>
            </div>
            <div className="bg-red-50 rounded p-2 text-center">
              <div className="text-red-700 font-semibold">${stock.or15_low?.toFixed(2)}</div>
              <div className="text-xs text-red-600">Low</div>
            </div>
          </div>
        </div>
      )}
      
      {/* 分类置信度 */}
      <div className="p-4 border-t border-gray-100">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-600">分类置信度</span>
          <span className="font-medium text-gray-800">{(stock.regime_confidence * 100).toFixed(0)}%</span>
        </div>
        <div className="bg-gray-200 rounded-full h-2">
          <div 
            className={`h-2 rounded-full ${
              stock.regime_confidence >= 0.7 ? 'bg-green-500' : 
              stock.regime_confidence >= 0.5 ? 'bg-yellow-500' : 'bg-red-500'
            }`}
            style={{ width: `${stock.regime_confidence * 100}%` }}
          />
        </div>
      </div>
      
      {/* 判断依据（可展开） */}
      <div className="border-t border-gray-100">
        <button
          onClick={onToggleExpand}
          className="w-full p-3 text-sm text-gray-600 hover:bg-gray-50 flex items-center justify-center gap-1"
        >
          {expanded ? '收起' : '展开'}判断依据
        </button>
        {expanded && (
          <div className="px-4 pb-4">
            <ul className="space-y-1">
              {stock.regime_reasons.map((reason, idx) => (
                <li key={idx} className="text-sm text-gray-600 flex items-start gap-2">
                  <span className="text-blue-500">•</span>
                  {reason}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      
      {/* 更新时间 */}
      <div className="px-4 py-2 bg-gray-50 text-xs text-gray-400 text-right">
        更新于 {stock.updated_at}
      </div>
    </div>
  );
}

// ============== 主应用 ==============

function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const [dataSource, setDataSourceState] = useState<DataSourceStatus>({
    current: 'yahoo',
    tws_available: false,
    tws_error: null
  });
  const [switchingSource, setSwitchingSource] = useState(false);
  const [timezone, setTimezone] = useState<TimezoneOption>('ET');

  const toggleCardExpand = (symbol: string) => {
    setExpandedCards(prev => {
      const newSet = new Set(prev);
      if (newSet.has(symbol)) {
        newSet.delete(symbol);
      } else {
        newSet.add(symbol);
      }
      return newSet;
    });
  };

  const loadData = useCallback(async (showRefresh = false) => {
    try {
      if (showRefresh) setRefreshing(true);
      const [dashboard, dsStatus] = await Promise.all([
        fetchDashboard(),
        getDataSource()
      ]);
      setData(dashboard);
      setDataSourceState(dsStatus);
      setError(null);
    } catch (err) {
      setError('无法连接到服务器，请确保后端已启动');
      console.error(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const handleSwitchDataSource = async (source: string) => {
    setSwitchingSource(true);
    try {
      const result = await setDataSource(source);
      setDataSourceState(result);
      // 重新加载数据
      await loadData();
    } catch (err) {
      console.error('切换数据源失败:', err);
    } finally {
      setSwitchingSource(false);
    }
  };

  useEffect(() => {
    loadData();
    // 每 30 秒刷新一次
    const interval = setInterval(() => loadData(), 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleAddSymbol = async (symbol: string): Promise<string | null> => {
    try {
      const result = await addToWatchlistWithValidation(symbol);
      if (result.success) {
        await loadData();
        return null; // 成功，无错误
      } else {
        return result.error || '添加失败';
      }
    } catch (err) {
      console.error('添加失败:', err);
      return '添加失败，请稍后重试';
    }
  };

  const handleRemoveSymbol = async (symbol: string) => {
    try {
      await removeFromWatchlist(symbol);
      await loadData();
    } catch (err) {
      console.error('移除失败:', err);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500 mx-auto mb-4" />
          <p className="text-gray-600">加载中...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="text-center bg-white p-8 rounded-lg shadow-md">
          <AlertTriangle className="w-12 h-12 text-orange-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-800 mb-2">连接失败</h2>
          <p className="text-gray-600 mb-4">{error}</p>
          <p className="text-sm text-gray-500 mb-4">
            请运行后端服务: <code className="bg-gray-100 px-2 py-1 rounded">uv run uvicorn tbot.api.main:app --reload</code>
          </p>
          <button
            onClick={() => loadData()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100">
      {/* 头部 */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Activity className="w-8 h-8 text-blue-500" />
            <h1 className="text-2xl font-bold text-gray-800">T-Trade Dashboard</h1>
          </div>
          <div className="flex items-center gap-4">
            {/* 时区选择 */}
            <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-1">
              <Globe className="w-4 h-4 text-gray-500 ml-2" />
              {(['ET', 'LOCAL', 'UTC'] as TimezoneOption[]).map((tz) => (
                <button
                  key={tz}
                  onClick={() => setTimezone(tz)}
                  className={`px-2 py-1 rounded-md text-xs font-medium transition-colors ${
                    timezone === tz
                      ? 'bg-white text-indigo-600 shadow-sm'
                      : 'text-gray-600 hover:text-gray-800'
                  }`}
                >
                  {TIMEZONE_LABELS[tz]}
                </button>
              ))}
            </div>
            
            {/* 数据源切换 */}
            <div className="flex items-center gap-2 bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => handleSwitchDataSource('yahoo')}
                disabled={switchingSource || dataSource.current === 'yahoo'}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  dataSource.current === 'yahoo'
                    ? 'bg-white text-blue-600 shadow-sm'
                    : 'text-gray-600 hover:text-gray-800'
                }`}
              >
                <Database className="w-4 h-4" />
                Yahoo
              </button>
              <button
                onClick={() => handleSwitchDataSource('tws')}
                disabled={switchingSource}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  dataSource.current === 'tws'
                    ? 'bg-white text-green-600 shadow-sm'
                    : 'text-gray-600 hover:text-gray-800'
                }`}
                title={dataSource.tws_error || '连接 TWS（数据仍来自 Yahoo）'}
              >
                {dataSource.tws_available ? (
                  <Wifi className="w-4 h-4 text-green-500" />
                ) : (
                  <WifiOff className="w-4 h-4 text-gray-400" />
                )}
                TWS
                {switchingSource && dataSource.current !== 'tws' && (
                  <RefreshCw className="w-3 h-3 animate-spin" />
                )}
              </button>
            </div>
            {/* 数据源状态提示 */}
            {dataSource.current === 'tws' && (
              <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded" title="已连接 TWS，数据来自 Yahoo">
                🟢 TWS 已连接
              </span>
            )}
            {dataSource.tws_error && dataSource.current !== 'tws' && (
              <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded" title={dataSource.tws_error}>
                TWS 未连接
              </span>
            )}
            <button
              onClick={() => loadData(true)}
              disabled={refreshing}
              className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              刷新
            </button>
          </div>
        </div>
      </header>

      {/* 主内容 */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* 市场状态 */}
        {data && (
          <MarketStatusCard
            session={data.market_status.session}
            progress={data.market_status.progress}
            tradingAllowed={data.market_status.trading_allowed}
            tradingReason={data.market_status.trading_reason}
            currentTime={data.market_status.current_time}
            timezone={timezone}
          />
        )}

        {/* Watchlist 管理 */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800">
              自选股 ({data?.watchlist.length || 0})
            </h2>
          </div>
          <WatchlistInput onAdd={handleAddSymbol} disabled={refreshing} />
          
          {/* 当前 Watchlist 标签 */}
          <div className="flex flex-wrap gap-2 mt-4">
            {data?.watchlist.map(symbol => (
              <span
                key={symbol}
                className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm"
              >
                {symbol}
                <button
                  onClick={() => handleRemoveSymbol(symbol)}
                  className="hover:bg-blue-200 rounded-full p-0.5"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        </div>

        {/* 股票卡片网格 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {data?.stocks.map(stock => (
            <StockCard
              key={stock.symbol}
              stock={stock}
              onRemove={handleRemoveSymbol}
              expanded={expandedCards.has(stock.symbol)}
              onToggleExpand={() => toggleCardExpand(stock.symbol)}
            />
          ))}
        </div>

        {/* 空状态 */}
        {data?.stocks.length === 0 && (
          <div className="text-center py-12">
            <Activity className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">没有自选股，添加一些股票开始监控</p>
          </div>
        )}
      </main>

      {/* 页脚 */}
      <footer className="text-center py-4 text-gray-400 text-sm">
        <div className="flex items-center justify-center gap-2">
          <span>T-Trade v0.1.0</span>
          <span>|</span>
          <span>数据源: Yahoo Finance {data?.data_source === 'tws' ? '(🟢 TWS 已连接)' : ''}</span>
          <span>|</span>
          <span>仅供参考，不构成投资建议</span>
        </div>
      </footer>
    </div>
  );
}

export default App;

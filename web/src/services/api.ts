export interface StatusResponse {
  ok: boolean;
  mode: string;
  execution_mode: string;
  is_live_armed: boolean;
  venue: string;
  worker_state: string;
  binance_connected: boolean;
  account: {
    balance: number;
    equity: number;
    free_margin: number;
    currency: string;
  };
  active_symbol: string;
  cycle_count: number;
  cycle_errors: number;
  candidate_count: number;
  last_candidate: string | null;
  last_candidate_symbol: string | null;
  last_candidate_score: number | null;
  last_decision: string | null;
  last_decision_at: string | null;
  last_reason: string | null;
  last_error: string | null;
  updated_at: string;
}

export interface CandidateItem {
  symbol: string;
  price: number;
  price_change_pct: number;
  score: number;
  tags?: string[];
}

export interface WatchlistData {
  timestamp: string;
  btc_report: {
    symbol: string;
    regime: string;
    trend_direction: string;
    funding_bias: string;
    recommendation_th: string;
  };
  candidates: CandidateItem[];
}

export interface ReadinessCheck {
  name: string;
  target: string;
  actual: string;
  passed: boolean;
  description: string;
}

export interface ReadinessData {
  ok: boolean;
  readiness_score: number;
  is_promotable: boolean;
  summary_th: string;
  checks: ReadinessCheck[];
  stats: Record<string, any>;
}

export interface PositionItem {
  ticket: number;
  symbol: string;
  direction: 'BUY' | 'SELL';
  volume: number;
  open_price: number;
  current_price: number;
  sl: number;
  tp: number;
  profit: number;
  pnl_pct: number;
}

export interface CandleItem {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CouncilLatest {
  ok: boolean;
  latest: {
    decision: string;
    candidate: string | null;
    symbol: string | null;
    score: number | null;
    reason: string;
    confluences: string[];
    vision_verdict?: {
      confirmed: boolean;
      confidence: number;
      rejection_wick: string;
      notes: string;
    } | null;
    timestamp: string | null;
  };
  history: any[];
}

const API_BASE = '/api';

export async function fetchStatus(): Promise<StatusResponse> {
  const res = await fetch(`${API_BASE}/status`);
  return res.json();
}

export async function fetchWatchlist(): Promise<{ ok: boolean; data: WatchlistData }> {
  const res = await fetch(`${API_BASE}/watchlist`);
  return res.json();
}

export async function fetchReadiness(): Promise<ReadinessData> {
  const res = await fetch(`${API_BASE}/readiness`);
  return res.json();
}

export async function fetchPositions(): Promise<{ ok: boolean; positions: PositionItem[] }> {
  const res = await fetch(`${API_BASE}/positions`);
  return res.json();
}

export async function fetchCandles(symbol: string, timeframe = '5m', count = 250): Promise<{ ok: boolean; symbol: string; timeframe: string; candles: CandleItem[] }> {
  const res = await fetch(`${API_BASE}/candles/${symbol}?timeframe=${timeframe}&count=${count}`);
  return res.json();
}

export async function fetchCouncilLatest(): Promise<CouncilLatest> {
  const res = await fetch(`${API_BASE}/council/latest`);
  return res.json();
}

export async function fetchTradeHistory(limit = 20): Promise<{ ok: boolean; trades: any[] }> {
  const res = await fetch(`${API_BASE}/history?limit=${limit}`);
  return res.json();
}

export async function triggerPanic(): Promise<{ ok: boolean; message: string; closed_count: number }> {
  const res = await fetch(`${API_BASE}/actions/panic`, { method: 'POST' });
  return res.json();
}

export async function triggerScan(): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/actions/scan`, { method: 'POST' });
  return res.json();
}

export async function closePosition(ticket: number, symbol = 'BTCUSDT'): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/actions/close_position`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket, symbol }),
  });
  return res.json();
}

export async function lockBreakEven(ticket: number, symbol = 'BTCUSDT'): Promise<{ ok: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/actions/break_even`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket, symbol }),
  });
  return res.json();
}

export async function setTradingMode(mode: 'PAPER' | 'LIVE', armed = false): Promise<{ ok: boolean; mode: string; is_live_armed: boolean }> {
  const res = await fetch(`${API_BASE}/actions/mode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode, armed }),
  });
  return res.json();
}

export interface RuntimeSettings {
  trading_mode: 'paper' | 'demo' | 'live';
  primary_symbol: string;
  active_symbols: string[];
  paper_initial_balance: number;
  risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_open_positions: number;
  min_rr: number;
  entry_min_score: number;
  max_consecutive_losses?: number;
  emergency_stop_loss_pct?: number;
  news_filter_enabled?: boolean;
  binance_mode: 'paper' | 'testnet' | 'live';
  binance_base_url: string;
  binance_api_key?: string;
  binance_api_secret?: string;
  ai_provider: 'codex' | 'openai' | 'gemini' | 'openrouter';
  openai_api_key?: string;
  openai_model?: string;
  gemini_api_key?: string;
  openrouter_api_key?: string;
  openrouter_model?: string;
  vision_provider?: 'deterministic' | 'gpt-4o' | 'claude-3-5' | 'deepseek-vision';
  vision_min_score?: number;
  volume_filter_enabled?: boolean;
  rsi_filter_enabled?: boolean;
  telegram_enabled: boolean;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  updated_at?: string;
}

export interface TradeMarkerItem {
  time: number;
  position: 'aboveBar' | 'belowBar';
  color: string;
  shape: 'arrowUp' | 'arrowDown' | 'circle' | 'square';
  text: string;
  id: string;
}

export interface TradeDetailItem {
  id: number;
  ticket: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  volume: number;
  entry_price: number;
  exit_price: number;
  sl: number;
  tp: number;
  profit: number;
  outcome_r: number;
  status: 'WIN' | 'LOSS' | 'BREAKEVEN' | 'OPEN';
  strategy: string;
  why_entered: string;
  why_won_lost: string;
  open_time: string | null;
  exit_time: string | null;
}

export interface BacktestRequest {
  strategy_id: string;
  symbol: string;
  timeframe: string;
  candle_count: number;
  initial_balance: number;
  risk_pct: number;
  spread_pips: number;
}

export interface BacktestSummary {
  strategy_id: string;
  symbol: string;
  timeframe: string;
  total_trades: number;
  winners: number;
  losers: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown: number;
  expectancy: number;
  sharpe_ratio: number;
  total_pnl: number;
  initial_balance: number;
  final_equity: number;
}

export interface BacktestTradeItem {
  id: number;
  direction: 'BUY' | 'SELL';
  entry: number;
  exit: number;
  pnl: number;
  status: 'WIN' | 'LOSS' | 'BREAKEVEN';
  r_multiple?: number;
  time?: string;
}

export interface BacktestResponse {
  ok: boolean;
  error?: string;
  summary: BacktestSummary;
  equity_curve: number[];
  trades: BacktestTradeItem[];
}

export async function fetchSettings(): Promise<{ ok: boolean; settings: RuntimeSettings }> {
  const res = await fetch(`${API_BASE}/settings`);
  return res.json();
}

export async function saveSettings(settings: Partial<RuntimeSettings>): Promise<{ ok: boolean; message: string; settings: RuntimeSettings }> {
  const res = await fetch(`${API_BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  return res.json();
}

export async function testBinanceApi(settings: Pick<RuntimeSettings, 'binance_mode' | 'binance_base_url' | 'binance_api_key' | 'binance_api_secret'>): Promise<{
  ok: boolean;
  message: string;
  balance?: number;
  equity?: number;
  currency?: string;
  status_code?: number;
}> {
  const res = await fetch(`${API_BASE}/settings/binance/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  return res.json();
}

export async function fetchTradeMarkers(symbol: string): Promise<{ ok: boolean; symbol: string; markers: TradeMarkerItem[]; trades: TradeDetailItem[] }> {
  const res = await fetch(`${API_BASE}/trades/markers?symbol=${symbol}`);
  return res.json();
}

export async function runBacktest(req: BacktestRequest): Promise<BacktestResponse> {
  const res = await fetch(`${API_BASE}/backtest/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  return res.json();
}

export interface AIAuthItem {
  id: string;
  name: string;
  auth_type: 'oauth-login' | 'api-key' | 'cli-login';
  state: 'authenticated' | 'configured' | 'login_required' | 'unknown';
  checked_at: string;
  account_label?: string;
  note: string;
}

export interface AIAuthResponse {
  ok: boolean;
  updated_at: string;
  items: AIAuthItem[];
}

export interface AITestResponse {
  ok: boolean;
  result: {
    ok: boolean;
    provider: string;
    status: 'ready' | 'login_required' | 'error' | 'exhausted';
    latency_ms: number;
    message: string;
    details?: any;
  };
}

export async function fetchAIAuthStatus(refresh = false): Promise<AIAuthResponse> {
  const res = await fetch(`${API_BASE}/ai/auth-status?refresh=${refresh}`);
  return res.json();
}

export async function testAIProvider(provider: string): Promise<AITestResponse> {
  const res = await fetch(`${API_BASE}/ai/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider }),
  });
  return res.json();
}

export interface ProFinancials {
  balance: number;
  equity: number;
  floating_pnl: number;
  deposit: number;
  today_pnl: number;
  today_trades: number;
  today_won: number;
  week_pnl: number;
  week_trades: number;
  month_pnl: number;
  month_trading_days: number;
  return_pct: number;
  profit_factor: number;
  win_rate_pct: number;
  drawdown_now_pct: number;
  drawdown_max_pct: number;
}

export interface StrategyLegItem {
  leg: string;
  id: string;
  name: string;
  status: string;
  status_color: string;
  today_pnl: number;
  month_pnl: number;
  trades_count: number;
  win_pct: number;
  pf: number;
  per_trade: string;
  last_20: number[];
}

export interface CalendarDayItem {
  day: number;
  trades: number;
  pnl: number;
  is_green: boolean | null;
  is_today: boolean;
  is_past: boolean;
}

export interface CalendarWeekItem {
  week: string;
  pnl: number;
  trades: number;
}

export interface CalendarSummary {
  month_name: string;
  month_pnl: number;
  green_days: number;
  total_active_days: number;
  best_day: number;
  best_day_date: number;
  worst_day: number;
  worst_day_date: number;
}

export interface ExecutionQualityLeg {
  leg: string;
  fills: number | null;
  entry_med: string;
  entry_p90: string;
  exit_med: string;
  worst: string;
  latency: number | null;
  slip_cost: number | null;
  slip_vs_edge: number | null;
}

export interface HourlySlipDistribution {
  hour: number;
  slip: number;
  status: string;
}

export interface ExecutionQuality {
  broker_grade: string;
  median_slip: string;
  p90_slip: string;
  slip_over_3_pct: number | null;
  avg_latency_ms: number | null;
  total_fills: number | null;
  slip_cost: number | null;
  legs: ExecutionQualityLeg[];
  hourly_distribution: HourlySlipDistribution[];
}

export interface EquityPoint {
  date: string;
  actual: number;
  edge: number;
}

export interface EquitySummary {
  closed_pnl: number;
  lost_to_slip: number | null;
  peak: number;
  from_peak: number;
  curve: EquityPoint[];
}

export interface LiveGuardItem {
  name: string;
  value: string;
  status: 'ok' | 'warning' | 'critical';
  desc: string;
}

export interface ProMetricsResponse {
  ok: boolean;
  symbol: string;
  updated_at: string;
  financials: ProFinancials;
  legs: StrategyLegItem[];
  total_leg: StrategyLegItem;
  calendar_days: CalendarDayItem[];
  weeks_summary: CalendarWeekItem[];
  calendar_summary: CalendarSummary;
  execution_quality: ExecutionQuality;
  equity_summary: EquitySummary;
  guards: LiveGuardItem[];
}

export async function fetchProMetrics(symbol = 'BTCUSDT'): Promise<ProMetricsResponse> {
  const res = await fetch(`${API_BASE}/analytics/pro-metrics?symbol=${symbol}`);
  return res.json();
}

export async function simulatePaperTrade(symbol = 'BTCUSDT', direction = 'BUY', strategy = 'CHoCH + Order Block'): Promise<any> {
  const res = await fetch(`${API_BASE}/actions/simulate_trade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, direction, strategy }),
  });
  return res.json();
}



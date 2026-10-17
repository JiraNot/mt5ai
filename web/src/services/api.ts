export interface StatusResponse {
  ok: boolean;
  mode: string;
  is_live_armed: boolean;
  venue: string;
  binance_connected: boolean;
  account: {
    balance: number;
    equity: number;
    free_margin: number;
    currency: string;
  };
  active_symbol: string;
  cycle_count: number;
  last_candidate: string | null;
  last_decision: string | null;
  last_reason: string | null;
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
    candidate: string;
    symbol: string;
    score: number;
    reason: string;
    confluences: string[];
    vision_verdict?: {
      confirmed: boolean;
      confidence: number;
      rejection_wick: string;
      notes: string;
    };
    timestamp: string;
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

export async function fetchTradeMarkers(symbol: string): Promise<{ ok: boolean; symbol: string; markers: TradeMarkerItem[]; trades: TradeDetailItem[] }> {
  const res = await fetch(`${API_BASE}/trades/markers?symbol=${symbol}`);
  return res.json();
}


import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  Shield,
  Zap,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  BarChart2,
  Calendar,
  Activity,
  ArrowUpRight,
  Sliders,
} from 'lucide-react';
import {
  fetchProMetrics,
  ProMetricsResponse,
  StrategyLegItem,
  CalendarDayItem,
  CalendarWeekItem,
  ExecutionQualityLeg,
  HourlySlipDistribution,
  LiveGuardItem,
  PositionItem,
  simulatePaperTrade
} from '../services/api';
import { StatusResponse } from '../services/api';

interface ProAnalyticsDashboardProps {
  symbol: string;
  status: StatusResponse | null;
  positions: PositionItem[];
  positionsLoaded: boolean;
  onSelectSymbol?: (symbol: string) => void;
  onSwitchToChart?: () => void;
}

export const ProAnalyticsDashboard: React.FC<ProAnalyticsDashboardProps> = ({
  symbol,
  status,
  positions,
  positionsLoaded,
  onSelectSymbol,
  onSwitchToChart,
}) => {
  const [data, setData] = useState<ProMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [hoveredPoint, setHoveredPoint] = useState<{ date: string; actual: number; edge: number } | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'slippage' | 'calendar'>('overview');

  const handleSimulateTrade = async () => {
    setSimulating(true);
    try {
      await simulatePaperTrade(symbol, 'BUY', 'CHoCH + Order Block');
      loadData(true);
    } catch (err: any) {
      alert('Simulate error: ' + err.message);
    } finally {
      setSimulating(false);
    }
  };

  // Global live clocks
  const [clocks, setClocks] = useState({
    utc: '',
    ny: '',
    bkk: '',
  });

  useEffect(() => {
    const updateClocks = () => {
      const now = new Date();
      setClocks({
        utc: now.toLocaleTimeString('en-US', { timeZone: 'UTC', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        ny: now.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit' }),
        bkk: now.toLocaleTimeString('en-US', { timeZone: 'Asia/Bangkok', hour12: false, hour: '2-digit', minute: '2-digit' }),
      });
    };
    updateClocks();
    const interval = setInterval(updateClocks, 1000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const res = await fetchProMetrics(symbol);
      if (res && res.ok) {
        setData(res);
      }
    } catch (err) {
      console.error('Error fetching pro metrics:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(() => loadData(false), 5000);
    return () => clearInterval(interval);
  }, [symbol]);

  if (loading && !data) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#070b14] text-slate-400">
        <div className="flex items-center space-x-3">
          <Activity className="w-5 h-5 text-brand-gold animate-spin" />
          <span className="font-mono text-sm tracking-wide">INITIALIZING INSTITUTIONAL DESK TELEMETRY...</span>
        </div>
      </div>
    );
  }

  const fin = data?.financials;
  const legs = data?.legs || [];
  const totalLeg = data?.total_leg;
  const calDays = data?.calendar_days || [];
  const weeks = data?.weeks_summary || [];
  const calSum = data?.calendar_summary;
  const exec = data?.execution_quality;
  const eqSum = data?.equity_summary;
  const guards = data?.guards || [];
  const recordedTradeLegs = legs.filter((leg: StrategyLegItem) => leg.trades_count > 0).length;
  const decisionLabels: Record<string, string> = {
    NO_CANDIDATE: 'NO SETUP',
    AI_SKIP: 'AI SCORE FILTERED',
    COUNCIL_SKIP: 'AI COUNCIL SKIPPED',
    RISK_REJECTED: 'RISK ENGINE REJECTED',
    ORDER_FAILED: 'ORDER FAILED',
    TRADE_EXECUTED: 'TRADE EXECUTED',
    RISK_APPROVED: 'RISK APPROVED',
    RECORDED_CANDIDATE: 'RECORDED CANDIDATE',
    NO_RECENT_DECISION: 'NO RECENT DECISION',
  };
  const decisionLabel = status?.last_decision
    ? decisionLabels[status.last_decision] ?? status.last_decision.replace(/_/g, ' ')
    : 'NO WORKER DECISION';
  const decisionDetail = status?.last_reason || status?.last_error || 'No pipeline result has been recorded yet.';
  const decisionTime = status?.last_decision_at
    ? new Date(status.last_decision_at).toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'short' })
    : 'not recorded';
  const workerRunning = status?.worker_state?.toLowerCase() === 'running';
  const systemHealthy = workerRunning && !!status?.binance_connected;
  const liveStateLabel = status
    ? status.is_live_armed ? 'LIVE ARMED' : 'LIVE DISARMED'
    : 'LIVE STATE UNKNOWN';
  const calendarMonthLabel = calSum?.month_name ?? new Date().toLocaleString('en-US', {
    month: 'long',
    year: 'numeric',
  });

  // SVG dimensions for equity curve
  const curvePoints = eqSum?.curve || [];
  const minEquity = curvePoints.length > 0 ? Math.min(...curvePoints.map(p => Math.min(p.actual, p.edge))) * 0.999 : 100000;
  const maxEquity = curvePoints.length > 0 ? Math.max(...curvePoints.map(p => Math.max(p.actual, p.edge))) * 1.001 : 105000;
  const svgWidth = 600;
  const svgHeight = 220;
  const paddingX = 40;
  const paddingY = 25;

  const getX = (index: number) => {
    if (curvePoints.length <= 1) return paddingX;
    return paddingX + (index / (curvePoints.length - 1)) * (svgWidth - paddingX * 2);
  };

  const getY = (val: number) => {
    const range = maxEquity - minEquity || 1;
    return svgHeight - paddingY - ((val - minEquity) / range) * (svgHeight - paddingY * 2);
  };

  const actualPath = curvePoints.reduce((acc, p, idx) => {
    const x = getX(idx);
    const y = getY(p.actual);
    return idx === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`;
  }, '');

  const edgePath = curvePoints.reduce((acc, p, idx) => {
    const x = getX(idx);
    const y = getY(p.edge);
    return idx === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`;
  }, '');

  // Shaded area between edge and actual
  let diffAreaPath = '';
  if (curvePoints.length > 1) {
    const forwardActual = curvePoints.map((p, idx) => `${getX(idx)},${getY(p.actual)}`).join(' L ');
    const backwardEdge = [...curvePoints].reverse().map((p, idx) => {
      const originalIdx = curvePoints.length - 1 - idx;
      return `${getX(originalIdx)},${getY(p.edge)}`;
    }).join(' L ');
    diffAreaPath = `M ${forwardActual} L ${backwardEdge} Z`;
  }

  return (
    <div className="flex-1 flex flex-col bg-[#070b14] text-slate-200 overflow-y-auto font-sans select-none custom-scrollbar pb-12">
      {/* 1. TOP TELEMETRY RIBBON (Institutional Prop Desk Header) */}
      <div className="bg-[#0b101f] border-b border-[#18233c] px-3.5 py-2 flex flex-wrap items-center justify-between gap-y-2 text-xs">
        {/* Left: Branding & Core Market State */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <span className={`w-2 h-2 rounded-full ${systemHealthy ? 'bg-emerald-400 animate-ping' : 'bg-rose-400'}`} />
            <span className="font-mono font-bold tracking-wider text-white text-xs">
              APEXTRADER <span className="text-brand-gold">AI PRO v0.10</span>
            </span>
          </div>

          <div className="h-4 w-px bg-slate-800" />

          {/* Symbol Pill */}
          <div className="flex items-center space-x-1.5 bg-[#121a30] border border-[#223154] px-2.5 py-0.5 rounded-full font-mono text-[11px]">
            <span className="font-bold text-amber-400">{symbol}</span>
          </div>
        </div>

        {/* Right: Real clocks and dashboard actions */}
        <div className="flex items-center space-x-3 text-[11px] font-mono">
          {/* Clocks */}
          <div className="hidden md:flex items-center space-x-2 text-slate-400">
            <span>UTC <strong className="text-slate-200">{clocks.utc}</strong></span>
            <span>NY <strong className="text-slate-200">{clocks.ny}</strong></span>
            <span>BKK <strong className="text-slate-200">{clocks.bkk}</strong></span>
          </div>

          {/* Refresh button */}
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="p-1 rounded hover:bg-[#1a2542] text-slate-400 hover:text-white transition-colors"
            title="อัปเดตข้อมูลสด"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-brand-gold' : ''}`} />
          </button>

          {/* Switch to Chart button */}
          {onSwitchToChart && (
            <button
              onClick={onSwitchToChart}
              className="px-2.5 py-1 rounded bg-[#16213c] hover:bg-[#202f56] border border-[#2b3c66] text-cyan-300 font-sans font-semibold flex items-center space-x-1 transition-all"
            >
              <BarChart2 className="w-3.5 h-3.5" />
              <span>CHART VIEW</span>
            </button>
          )}
        </div>
      </div>

      {/* Live worker and decision telemetry */}
      <div className="mx-3.5 mt-2 rounded-lg border border-[#18233c] bg-[#0b101f] px-3 py-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11px] font-mono">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-slate-400">
          <span className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${workerRunning ? 'bg-emerald-400' : 'bg-rose-400'}`} />
            WORKER <strong className={workerRunning ? 'text-emerald-400' : 'text-rose-300'}>{status?.worker_state?.toUpperCase() ?? 'UNKNOWN'}</strong>
          </span>
          <span>MARKET DATA <strong className={status?.binance_connected ? 'text-emerald-400' : 'text-rose-300'}>{status?.binance_connected ? 'CONNECTED' : 'DISCONNECTED'}</strong></span>
          <span>EXECUTION <strong className="text-slate-200">{status?.execution_mode?.toUpperCase() ?? 'UNKNOWN'}</strong></span>
          <span>CYCLES <strong className="text-slate-200">{status?.cycle_count ?? 0}</strong></span>
          <span>CANDIDATES <strong className="text-slate-200">{status?.candidate_count ?? 0}</strong></span>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 text-slate-300">
          <span className="text-brand-gold font-bold">{decisionLabel}</span>
          {status?.last_candidate && <span>{status.last_candidate_symbol} · {status.last_candidate}</span>}
          <span className="break-all">{decisionDetail}</span>
          <span className="text-slate-500">{decisionTime}</span>
        </div>
      </div>

      {/* 2. EXECUTIVE 6 FINANCIAL CARDS (Institutional Capital Strip) */}
      <div className="p-3.5 pb-2 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5">
        {/* Card 1: Balance */}
        <div className="bg-[#0b101f] border border-[#18233c] hover:border-[#28385e] rounded-lg p-3 transition-colors">
          <div className="text-[10px] font-mono font-semibold tracking-wider text-slate-400 uppercase">Balance</div>
          <div className="text-base sm:text-lg font-mono font-bold text-white mt-0.5">
            {fin ? `$${fin.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
          </div>
          <div className="text-[10px] font-mono text-emerald-400 flex items-center space-x-0.5 mt-0.5">
            <ArrowUpRight className="w-3 h-3" />
            <span>{fin ? `+$${(fin.balance - fin.deposit).toLocaleString(undefined, { minimumFractionDigits: 2 })} all-time` : '—'}</span>
          </div>
        </div>

        {/* Card 2: Equity */}
        <div className="bg-[#0b101f] border border-[#18233c] hover:border-[#28385e] rounded-lg p-3 transition-colors">
          <div className="text-[10px] font-mono font-semibold tracking-wider text-slate-400 uppercase">Equity</div>
          <div className="text-base sm:text-lg font-mono font-bold text-cyan-300 mt-0.5">
            {fin ? `$${fin.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
          </div>
          <div className="text-[10px] font-mono text-cyan-400 flex items-center space-x-1 mt-0.5">
            <span>{fin ? `Float ${fin.floating_pnl >= 0 ? '+' : ''}$${fin.floating_pnl.toFixed(2)}` : 'Float —'}</span>
            <span className="text-slate-600">•</span>
            <span className="text-emerald-400">{fin ? (fin.today_trades ? `${fin.today_trades} trade` : '0 trades') : '—'}</span>
          </div>
        </div>

        {/* Card 3: Today */}
        <div className="bg-[#0b101f] border border-[#18233c] hover:border-[#28385e] rounded-lg p-3 transition-colors">
          <div className="text-[10px] font-mono font-semibold tracking-wider text-slate-400 uppercase">Today</div>
          <div className="text-base sm:text-lg font-mono font-bold text-emerald-400 mt-0.5">
            {fin ? `${fin.today_pnl >= 0 ? '+' : '-'}$${Math.abs(fin.today_pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
          </div>
          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
            {fin ? <>{fin.today_won} / {fin.today_trades} won • <span className="text-emerald-400 font-semibold">{fin.today_trades ? ((fin.today_won / fin.today_trades) * 100).toFixed(1) : '0.0'}%</span></> : '—'}
          </div>
        </div>

        {/* Card 4: This Week */}
        <div className="bg-[#0b101f] border border-[#18233c] hover:border-[#28385e] rounded-lg p-3 transition-colors">
          <div className="text-[10px] font-mono font-semibold tracking-wider text-slate-400 uppercase">This Week</div>
          <div className="text-base sm:text-lg font-mono font-bold text-emerald-400 mt-0.5">
            {fin ? `${fin.week_pnl >= 0 ? '+' : '-'}$${Math.abs(fin.week_pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
          </div>
          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
            {fin ? `${fin.week_trades} trades` : '—'}
          </div>
        </div>

        {/* Card 5: This Month */}
        <div className="bg-[#0b101f] border border-[#18233c] hover:border-[#28385e] rounded-lg p-3 transition-colors">
          <div className="text-[10px] font-mono font-semibold tracking-wider text-slate-400 uppercase">This Month</div>
          <div className="text-base sm:text-lg font-mono font-bold text-emerald-400 mt-0.5">
            {fin ? `${fin.month_pnl >= 0 ? '+' : '-'}$${Math.abs(fin.month_pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
          </div>
          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
            {fin ? `${fin.month_trading_days} active days` : '—'}
          </div>
        </div>

        {/* Card 6: Performance Ratio */}
        <div className="bg-[#0b101f] border border-[#18233c] hover:border-[#28385e] rounded-lg p-3 transition-colors">
          <div className="text-[10px] font-mono font-semibold tracking-wider text-slate-400 uppercase">Return / Drawdown</div>
          <div className="text-base sm:text-lg font-mono font-bold text-brand-gold mt-0.5">
            {fin ? `${fin.return_pct >= 0 ? '+' : ''}${fin.return_pct}%` : '—'}
          </div>
          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
            {fin ? <>PF <strong className="text-slate-200">{fin.profit_factor}</strong> • DD <strong className="text-amber-400">{fin.drawdown_now_pct}%</strong> <span className="text-[9px] text-slate-500">(max {fin.drawdown_max_pct}%)</span></> : '—'}
          </div>
        </div>
      </div>

      {/* 3. MULTI-STRATEGY LEGS BREAKDOWN TABLE (Fast, Session, Core, Wide) */}
      <div className="px-3.5 py-1.5">
        <div className="bg-[#0b101f] border border-[#18233c] rounded-lg overflow-hidden">
          <div className="px-3.5 py-2 border-b border-[#18233c] flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="w-1.5 h-3.5 rounded-full bg-brand-gold" />
              <span className="font-mono font-bold text-xs text-white uppercase tracking-wider">
                STRATEGY LEGS ARCHITECTURE & CONFLUENCE
              </span>
              <span className="text-[11px] text-slate-400 font-mono hidden sm:inline">
                (Historical trade outcomes by strategy)
              </span>
            </div>
            <div className="text-[11px] font-mono text-slate-400">
              Closed trade history: <span className="text-slate-200 font-bold">{recordedTradeLegs} / {legs.length} strategies</span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-[11px]">
              <thead className="bg-[#0f162b] text-slate-400 uppercase text-[10px] border-b border-[#18233c]">
                <tr>
                  <th className="py-2 px-3">Leg</th>
                  <th className="py-2 px-3">Strategy Engine</th>
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3 text-right">Today</th>
                  <th className="py-2 px-3 text-right">Month</th>
                  <th className="py-2 px-3 text-center">Trades</th>
                  <th className="py-2 px-3 text-center">Win %</th>
                  <th className="py-2 px-3 text-center">PF</th>
                  <th className="py-2 px-3 text-center">Avg R</th>
                  <th className="py-2 px-3">Last 20 Trades (Tick Flow)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#141d33]">
                {legs.map((leg: StrategyLegItem) => (
                  <tr key={leg.leg} className="hover:bg-[#111930] transition-colors">
                    {/* Leg tag */}
                    <td className="py-2 px-3 font-bold text-amber-400">{leg.leg}</td>

                    {/* Name */}
                    <td className="py-2 px-3 text-slate-200 font-semibold">{leg.name}</td>

                    {/* Status pill */}
                    <td className="py-2 px-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          leg.status_color === 'emerald'
                            ? 'bg-emerald-500/15 border border-emerald-500/40 text-emerald-400'
                            : leg.status_color === 'sky'
                            ? 'bg-sky-500/15 border border-sky-500/40 text-sky-400'
                            : leg.status_color === 'purple'
                            ? 'bg-purple-500/15 border border-purple-500/40 text-purple-300'
                            : leg.status_color === 'slate'
                            ? 'bg-slate-500/10 border border-slate-500/30 text-slate-400'
                            : 'bg-amber-500/15 border border-amber-500/40 text-amber-400'
                        }`}
                      >
                        {leg.status}
                      </span>
                    </td>

                    {/* Today PnL */}
                    <td className={`py-2 px-3 text-right font-bold ${leg.today_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {leg.today_pnl >= 0 ? `+$${leg.today_pnl.toFixed(2)}` : `-$${Math.abs(leg.today_pnl).toFixed(2)}`}
                    </td>

                    {/* Month PnL */}
                    <td className="py-2 px-3 text-right text-emerald-400 font-bold">
                      +${leg.month_pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>

                    {/* Trades count */}
                    <td className="py-2 px-3 text-center text-slate-300">{leg.trades_count}</td>

                    {/* Win % */}
                    <td className="py-2 px-3 text-center text-slate-200 font-semibold">{leg.win_pct}%</td>

                    {/* PF */}
                    <td className="py-2 px-3 text-center text-slate-300">{leg.pf.toFixed(2)}</td>

                    {/* Avg R */}
                    <td className="py-2 px-3 text-center text-emerald-400 font-semibold">{leg.per_trade}</td>

                    {/* Last 20 sparkline ticks */}
                    <td className="py-2 px-3">
                      <div className="flex items-center space-x-1">
                        {leg.last_20.map((outcome, i) => (
                          <div
                            key={i}
                            title={outcome === 1 ? 'Win' : outcome === -1 ? 'Loss' : 'Breakeven'}
                            className={`w-1.5 h-3.5 rounded-2xs ${
                              outcome === 1
                                ? 'bg-emerald-400 shadow-xs shadow-emerald-500/50'
                                : outcome === -1
                                ? 'bg-rose-500'
                                : 'bg-slate-600'
                            }`}
                          />
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}

                {/* Total Row */}
                {totalLeg && (
                  <tr className="bg-[#121c38] font-bold border-t-2 border-[#203056]">
                    <td className="py-2 px-3 text-amber-300">{totalLeg.leg}</td>
                    <td className="py-2 px-3 text-white">{totalLeg.name}</td>
                    <td className="py-2 px-3">
                      <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/40">
                        {totalLeg.status}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right text-emerald-300">
                      +${totalLeg.today_pnl.toFixed(2)}
                    </td>
                    <td className="py-2 px-3 text-right text-emerald-300">
                      +${totalLeg.month_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="py-2 px-3 text-center text-white">{totalLeg.trades_count}</td>
                    <td className="py-2 px-3 text-center text-emerald-400">{totalLeg.win_pct}%</td>
                    <td className="py-2 px-3 text-center text-amber-300">{totalLeg.pf.toFixed(2)}</td>
                    <td className="py-2 px-3 text-center text-emerald-300">{totalLeg.per_trade}</td>
                    <td className="py-2 px-3">
                      <div className="flex items-center space-x-1">
                        {totalLeg.last_20.map((outcome, i) => (
                          <div
                            key={i}
                            className={`w-1.5 h-3.5 rounded-2xs ${
                              outcome === 1 ? 'bg-emerald-400' : outcome === -1 ? 'bg-rose-500' : 'bg-slate-600'
                            }`}
                          />
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* 4. MAIN SPLIT: LEFT (Calendar Heatmap + Execution Quality) & RIGHT (Dual-Line Curve + Guards) */}
      <div className="px-3.5 py-1.5 grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* ================= LEFT 7 COLS: CALENDAR HEATMAP & EXECUTION QUALITY ================= */}
        <div className="lg:col-span-7 flex flex-col space-y-3">
          {/* DAILY P/L CALENDAR HEATMAP */}
          <div className="bg-[#0b101f] border border-[#18233c] rounded-lg overflow-hidden flex flex-col">
            {/* Header */}
            <div className="px-3.5 py-2 border-b border-[#18233c] flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center space-x-2">
                <Calendar className="w-3.5 h-3.5 text-brand-gold" />
                <span className="font-mono font-bold text-xs text-white uppercase tracking-wider">
                  DAILY P/L CALENDAR ({calendarMonthLabel})
                </span>
              </div>
              <div className="flex items-center space-x-3 text-[11px] font-mono">
                <span className="text-slate-400">
                  Green Days: <strong className="text-emerald-400">{calSum?.green_days ?? 0}</strong> / {calSum?.total_active_days ?? 0} ({(((calSum?.green_days ?? 0) / (calSum?.total_active_days || 1)) * 100).toFixed(1)}%)
                </span>
                <span className="text-slate-600 hidden sm:inline">•</span>
                <span className="text-slate-400 hidden sm:inline">
                  Best: <strong className="text-emerald-400">+${calSum?.best_day ?? 0}</strong>
                </span>
                <span className="text-slate-600 hidden sm:inline">•</span>
                <span className="text-slate-400 hidden sm:inline">
                  Worst: <strong className="text-rose-400">-${Math.abs(calSum?.worst_day ?? 0)}</strong>
                </span>
              </div>
            </div>

            {/* Calendar Grid */}
            <div className="p-3">
              {/* Day headers */}
              <div className="grid grid-cols-8 gap-1.5 text-center font-mono text-[10px] text-slate-400 uppercase font-semibold mb-1">
                <div>Mon</div>
                <div>Tue</div>
                <div>Wed</div>
                <div>Thu</div>
                <div>Fri</div>
                <div className="text-slate-600">Sat</div>
                <div className="text-slate-600">Sun</div>
                <div className="text-amber-400">Week</div>
              </div>

              {/* Rows: 5 weeks */}
              <div className="space-y-1.5">
                {[0, 1, 2, 3, 4].map((weekIdx) => {
                  const weekItem = weeks[weekIdx];
                  return (
                    <div key={weekIdx} className="grid grid-cols-8 gap-1.5 text-xs font-mono">
                      {[0, 1, 2, 3, 4, 5, 6].map((dayOfWeek) => {
                        const dayNum = weekIdx * 7 + dayOfWeek + 1;
                        if (dayNum > 31) {
                          return <div key={dayOfWeek} className="h-14 bg-[#080d1a]/40 rounded border border-transparent" />;
                        }
                        const cell = calDays.find((d: CalendarDayItem) => d.day === dayNum);
                        const hasTrades = cell && cell.trades > 0;
                        const isGreen = cell && cell.pnl > 0;
                        const isRed = cell && cell.pnl < 0;

                        return (
                          <div
                            key={dayOfWeek}
                            className={`h-14 rounded border p-1.5 flex flex-col justify-between transition-all ${
                              cell?.is_today
                                ? 'border-brand-gold bg-[#141e38] shadow-sm shadow-brand-gold/20'
                                : hasTrades
                                ? isGreen
                                  ? 'border-emerald-500/30 bg-emerald-500/10 hover:border-emerald-500/50'
                                  : 'border-rose-500/30 bg-rose-500/10 hover:border-rose-500/50'
                                : 'border-[#141e33] bg-[#0a0f20]/50 text-slate-600'
                            }`}
                          >
                            <div className="flex items-center justify-between text-[10px]">
                              <span className={`font-bold ${cell?.is_today ? 'text-brand-gold' : hasTrades ? 'text-slate-300' : 'text-slate-600'}`}>
                                {dayNum}
                              </span>
                              {hasTrades && (
                                <span className="text-[9px] bg-[#111c38] px-1 rounded text-slate-400">
                                  {cell.trades} tr
                                </span>
                              )}
                            </div>

                            <div className="text-right">
                              {hasTrades ? (
                                <div className={`font-bold text-[11px] ${isGreen ? 'text-emerald-400' : isRed ? 'text-rose-400' : 'text-slate-400'}`}>
                                  {cell.pnl > 0 ? `+${cell.pnl.toFixed(2)}` : cell.pnl.toFixed(2)}
                                </div>
                              ) : (
                                <div className="text-[10px] text-slate-700">-</div>
                              )}
                            </div>
                          </div>
                        );
                      })}

                      {/* Weekly Total Column */}
                      <div className="h-14 rounded border border-amber-500/20 bg-amber-500/5 p-1.5 flex flex-col justify-between text-right">
                        <div className="text-[10px] font-bold text-amber-400/90 text-left">
                          {weekItem?.week || `W${weekIdx + 1}`}
                        </div>
                        {weekItem ? (
                          <div>
                            <div className="text-[9px] text-slate-400">{weekItem.trades} tr</div>
                            <div className={`font-bold text-[11px] ${weekItem.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {weekItem.pnl >= 0 ? `+$${weekItem.pnl.toFixed(2)}` : `-$${Math.abs(weekItem.pnl).toFixed(2)}`}
                            </div>
                          </div>
                        ) : (
                          <div className="text-slate-600">-</div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* EXECUTION QUALITY & SLIPPAGE ANALYTICS */}
          <div className="bg-[#0b101f] border border-[#18233c] rounded-lg overflow-hidden">
            {/* Header */}
            <div className="px-3.5 py-2 border-b border-[#18233c] flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center space-x-2">
                <Sliders className="w-3.5 h-3.5 text-cyan-400" />
                <span className="font-mono font-bold text-xs text-white uppercase tracking-wider">
                  EXECUTION QUALITY & SLIPPAGE FRICTION
                </span>
                <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-500/10 text-slate-300 font-mono font-bold border border-slate-500/30">
                  {exec?.broker_grade ?? 'NOT TRACKED'}
                </span>
              </div>
              <div className="flex items-center space-x-3 text-[11px] font-mono text-slate-400">
                <span>Median: <strong className="text-slate-200">{exec?.median_slip ?? '—'} pt</strong></span>
                <span>P90: <strong className="text-slate-200">{exec?.p90_slip ?? '—'} pt</strong></span>
                <span>Slip &gt; 3pt: <strong className="text-amber-400">{exec?.slip_over_3_pct ?? '—'}{exec?.slip_over_3_pct == null ? '' : '%'}</strong></span>
                <span>Latency: <strong className="text-cyan-400">{exec?.avg_latency_ms ?? '—'}{exec?.avg_latency_ms == null ? '' : 'ms'}</strong></span>
              </div>
            </div>

            {/* Table of Slippage per leg */}
            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-[11px]">
                <thead className="bg-[#0f162b] text-slate-400 uppercase text-[10px] border-b border-[#18233c]">
                  <tr>
                    <th className="py-2 px-3">Leg</th>
                    <th className="py-2 px-3 text-center">Fills</th>
                    <th className="py-2 px-3 text-right">Entry Med</th>
                    <th className="py-2 px-3 text-right">Entry P90</th>
                    <th className="py-2 px-3 text-right">Exit Med</th>
                    <th className="py-2 px-3 text-right">Worst</th>
                    <th className="py-2 px-3 text-center">Latency</th>
                    <th className="py-2 px-3 text-right">Slip Cost</th>
                    <th className="py-2 px-3">Slip vs Edge Ratio</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#141d33]">
                  {exec?.legs.map((l: ExecutionQualityLeg) => (
                    <tr key={l.leg} className={`hover:bg-[#111930] transition-colors ${l.leg === 'All' ? 'bg-[#121c38] font-bold border-t border-[#203056]' : ''}`}>
                      <td className="py-2 px-3 text-amber-400 font-bold">{l.leg}</td>
                      <td className="py-2 px-3 text-center text-slate-300">{l.fills ?? '—'}</td>
                      <td className="py-2 px-3 text-right text-slate-200">{l.entry_med} pt</td>
                      <td className="py-2 px-3 text-right text-slate-300">{l.entry_p90} pt</td>
                      <td className="py-2 px-3 text-right text-slate-300">{l.exit_med} pt</td>
                      <td className="py-2 px-3 text-right text-rose-400">{l.worst} pt</td>
                      <td className="py-2 px-3 text-center text-cyan-300">{l.latency == null ? '—' : `${l.latency}ms`}</td>
                      <td className="py-2 px-3 text-right text-rose-400">{l.slip_cost == null ? '—' : `$${l.slip_cost}`}</td>
                      <td className="py-2 px-3">
                        {l.slip_vs_edge == null ? '—' : (
                          <div className="flex items-center space-x-2">
                            <div className="w-20 bg-dark-800 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="bg-amber-400 h-full rounded-full"
                                style={{ width: `${Math.min(l.slip_vs_edge, 100)}%` }}
                              />
                            </div>
                            <span className="text-[10px] text-slate-400">{l.slip_vs_edge}% edge</span>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Hourly slippage bar chart */}
            <div className="p-3 bg-[#090e1c] border-t border-[#18233c] flex flex-wrap items-center justify-between gap-2">
              <span className="text-[10px] font-mono text-slate-400 uppercase font-semibold">
                Hourly Slippage Distribution (UTC):
              </span>
              {exec?.hourly_distribution.length ? (
                <div className="flex items-center space-x-2.5">
                  {exec.hourly_distribution.map((h: HourlySlipDistribution) => (
                  <div key={h.hour} className="flex flex-col items-center space-y-1">
                    <div
                      className={`w-3.5 rounded-2xs ${
                        h.status === 'high' ? 'bg-rose-500' : h.status === 'mid' ? 'bg-amber-400' : 'bg-emerald-400'
                      }`}
                      style={{ height: `${Math.max(h.slip * 16, 6)}px` }}
                      title={`${h.hour}:00 UTC - ${h.slip} pt slip`}
                    />
                    <span className="text-[9px] font-mono text-slate-500">{h.hour}h</span>
                  </div>
                  ))}
                </div>
              ) : (
                <span className="text-[10px] text-slate-500 font-mono">No slippage samples recorded</span>
              )}
            </div>
          </div>
        </div>

        {/* ================= RIGHT 5 COLS: DUAL-LINE EQUITY CURVE & SAFETY GUARDS ================= */}
        <div className="lg:col-span-5 flex flex-col space-y-3">
          {/* DUAL-LINE EQUITY & GROSS EDGE CURVE */}
          <div className="bg-[#0b101f] border border-[#18233c] rounded-lg overflow-hidden flex flex-col">
            {/* Header */}
            <div className="px-3.5 py-2 border-b border-[#18233c] flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center space-x-2">
                <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
                <span className="font-mono font-bold text-xs text-white uppercase tracking-wider">
                  REALIZED EQUITY VS GROSS P&L
                </span>
              </div>
              <div className="flex items-center space-x-3 text-[10px] font-mono">
                <div className="flex items-center space-x-1">
                  <span className="w-2 h-2 rounded-full bg-cyan-400" />
                  <span className="text-cyan-300 font-semibold">Actual Equity</span>
                </div>
                <div className="flex items-center space-x-1">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  <span className="text-amber-300 font-semibold">Gross P&amp;L</span>
                </div>
              </div>
            </div>

            {/* Performance Strip above chart */}
            <div className="px-3.5 py-2 bg-[#090e1c] border-b border-[#141e33] grid grid-cols-4 gap-2 text-center font-mono">
              <div>
                <div className="text-[9px] text-slate-500 uppercase">Closed P&L</div>
                <div className="text-xs font-bold text-emerald-400">
                  {eqSum ? `${eqSum.closed_pnl >= 0 ? '+' : '-'}$${Math.abs(eqSum.closed_pnl).toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '—'}
                </div>
              </div>
              <div>
                <div className="text-[9px] text-slate-500 uppercase">Slippage Cost</div>
                <div className="text-xs font-bold text-rose-400">
                  {eqSum?.lost_to_slip == null ? '—' : `$${eqSum.lost_to_slip.toFixed(2)}`}
                </div>
              </div>
              <div>
                <div className="text-[9px] text-slate-500 uppercase">Peak</div>
                <div className="text-xs font-bold text-white">
                  {eqSum ? `$${eqSum.peak.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '—'}
                </div>
              </div>
              <div>
                <div className="text-[9px] text-slate-500 uppercase">From Peak</div>
                <div className="text-xs font-bold text-emerald-400">
                  {eqSum ? `${eqSum.from_peak >= 0 ? '+' : ''}${eqSum.from_peak}%` : '—'}
                </div>
              </div>
            </div>

            {/* SVG Interactive Dual Line Chart */}
            <div className="p-2 relative flex items-center justify-center bg-[#070c18]">
              {curvePoints.length === 0 ? (
                <div className="w-full h-40 flex items-center justify-center text-xs font-mono text-slate-500">
                  No equity history available
                </div>
              ) : (
              <svg
                viewBox={`0 0 ${svgWidth} ${svgHeight}`}
                className="w-full h-auto overflow-visible"
              >
                <defs>
                  {/* Subtle gradient for realized equity area */}
                  <linearGradient id="cyanGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#00d4ff" stopOpacity="0.25" />
                    <stop offset="100%" stopColor="#00d4ff" stopOpacity="0.0" />
                  </linearGradient>
                  {/* Slippage diff gradient */}
                  <linearGradient id="slipDiffGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.18" />
                    <stop offset="100%" stopColor="#ef4444" stopOpacity="0.08" />
                  </linearGradient>
                </defs>

                {/* Horizontal reference lines */}
                {[0.25, 0.5, 0.75].map((ratio) => {
                  const y = paddingY + ratio * (svgHeight - paddingY * 2);
                  const val = maxEquity - ratio * (maxEquity - minEquity);
                  return (
                    <g key={ratio}>
                      <line
                        x1={paddingX}
                        y1={y}
                        x2={svgWidth - paddingX}
                        y2={y}
                        stroke="#141e33"
                        strokeDasharray="3 3"
                      />
                      <text
                        x={svgWidth - paddingX + 5}
                        y={y + 3}
                        fill="#475569"
                        fontSize="9"
                        fontFamily="monospace"
                      >
                        ${val.toFixed(0)}
                      </text>
                    </g>
                  );
                })}

                {/* Slippage gap area */}
                {diffAreaPath && (
                  <path d={diffAreaPath} fill="url(#slipDiffGrad)" />
                )}

                {/* Golden Edge Line (Theoretical without slippage) */}
                <path
                  d={edgePath}
                  fill="none"
                  stroke="#fbbf24"
                  strokeWidth="1.75"
                  strokeDasharray="4 2"
                />

                {/* Cyan Actual Equity Line (Realized) */}
                <path
                  d={actualPath}
                  fill="none"
                  stroke="#00d4ff"
                  strokeWidth="2.5"
                />

                {/* Data points on hover */}
                {curvePoints.map((pt, idx) => {
                  const x = getX(idx);
                  const y = getY(pt.actual);
                  return (
                    <circle
                      key={idx}
                      cx={x}
                      cy={y}
                      r={hoveredPoint?.date === pt.date ? 4.5 : 2}
                      fill={hoveredPoint?.date === pt.date ? '#ffffff' : '#00d4ff'}
                      className="cursor-pointer transition-all"
                      onMouseEnter={() => setHoveredPoint(pt)}
                      onMouseLeave={() => setHoveredPoint(null)}
                    />
                  );
                })}
              </svg>
              )}

              {/* Hover Tooltip Overlay */}
              {hoveredPoint && (
                <div className="absolute top-4 left-6 bg-[#0f172a] border border-cyan-500/40 rounded p-2 text-[10px] font-mono shadow-xl z-10 pointer-events-none">
                  <div className="text-slate-400 font-bold border-b border-slate-800 pb-1 mb-1">
                    {hoveredPoint.date}
                  </div>
                  <div className="text-cyan-300 font-semibold">
                    Realized Equity: ${hoveredPoint.actual.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-amber-300 font-semibold">
                    Gross Edge: ${hoveredPoint.edge.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-rose-400 text-[9px] mt-0.5">
                    Gross-to-Net Difference: ${(hoveredPoint.edge - hoveredPoint.actual).toFixed(2)}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* REAL-TIME CIRCUIT BREAKERS & SAFETY GUARDS */}
          <div className="bg-[#0b101f] border border-[#18233c] rounded-lg overflow-hidden">
            <div className="px-3.5 py-2 border-b border-[#18233c] flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Shield className="w-3.5 h-3.5 text-emerald-400" />
                <span className="font-mono font-bold text-xs text-white uppercase tracking-wider">
                  SYSTEM & RISK GUARDS
                </span>
              </div>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border font-bold ${
                !status ? 'text-slate-400 bg-slate-500/10 border-slate-500/30' : status.is_live_armed
                  ? 'text-amber-300 bg-amber-500/10 border-amber-500/30'
                  : 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
              }`}>
                {liveStateLabel}
              </span>
            </div>

            <div className="p-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
              {guards.map((guard: LiveGuardItem) => (
                <div
                  key={guard.name}
                  className={`p-2 rounded border flex flex-col justify-between ${
                    guard.status === 'ok'
                      ? 'bg-emerald-500/5 border-emerald-500/20'
                      : guard.status === 'warning'
                      ? 'bg-amber-500/5 border-amber-500/20'
                      : 'bg-rose-500/5 border-rose-500/20'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400 font-semibold">{guard.name}</span>
                    {guard.status === 'ok' ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                    )}
                  </div>
                  <div className="mt-1 font-bold text-white text-[11px]">{guard.value}</div>
                  <div className="text-[9px] text-slate-500 mt-0.5">{guard.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* ACTIVE POSITION RISK MONITOR */}
          <div className="bg-[#0b101f] border border-[#18233c] rounded-lg overflow-hidden">
            <div className="px-3.5 py-2 border-b border-[#18233c] flex items-center justify-between">
              <span className="font-mono font-bold text-xs text-white uppercase tracking-wider">
                OPEN POSITIONS
              </span>
              <button
                onClick={handleSimulateTrade}
                disabled={simulating}
                className="px-2.5 py-0.5 rounded text-[10px] bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-bold hover:bg-emerald-500/25 transition-all flex items-center space-x-1"
                title="จำลองให้ AI เปิดออเดอร์ซ้อมเทรดตามโครงสร้าง SMC ทันที"
              >
                <Zap className={`w-3 h-3 ${simulating ? 'animate-spin' : ''}`} />
                <span>{simulating ? 'กำลังส่งคำสั่ง...' : '+ ซ้อมเปิดไม้จำลอง'}</span>
              </button>
            </div>
            <div className="p-3 font-mono text-xs space-y-2">
              {!positionsLoaded ? (
                <div className="text-slate-500">Position data unavailable</div>
              ) : positions.length === 0 ? (
                <div className="text-slate-500">No open positions returned by the API</div>
              ) : positions.map((position: PositionItem) => (
                <div key={position.ticket} className="py-1.5 border-b border-[#141e33] last:border-0">
                  <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                    <div className="flex items-center space-x-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${position.direction === 'BUY' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'}`}>
                        {position.direction}
                      </span>
                      <span className="text-white font-bold">{position.symbol}</span>
                      <span className="text-slate-400 text-[10px]">{position.volume.toLocaleString()} units</span>
                    </div>
                    <div className={`font-bold ${position.profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {position.profit >= 0 ? '+' : '-'}${Math.abs(position.profit).toFixed(2)} ({position.pnl_pct >= 0 ? '+' : ''}{position.pnl_pct.toFixed(2)}%)
                    </div>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 text-[10px] text-slate-400">
                    <div>Entry: <strong className="text-slate-200">{position.open_price.toLocaleString()}</strong></div>
                    <div>Mark: <strong className="text-slate-200">{position.current_price.toLocaleString()}</strong></div>
                    <div>SL: <strong className="text-rose-400">{position.sl > 0 ? position.sl.toLocaleString() : '—'}</strong></div>
                    <div>TP: <strong className="text-emerald-400">{position.tp > 0 ? position.tp.toLocaleString() : '—'}</strong></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

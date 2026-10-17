import React, { useState } from 'react';
import {
  X,
  Play,
  TrendingUp,
  Percent,
  DollarSign,
  ShieldAlert,
  Award,
  RefreshCw,
  BarChart3,
  Calendar,
  Layers,
} from 'lucide-react';
import { runBacktest, BacktestRequest, BacktestResponse } from '../services/api';

interface BacktestModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeSymbol?: string;
}

export const BacktestModal: React.FC<BacktestModalProps> = ({ isOpen, onClose, activeSymbol = 'BTCUSDT' }) => {
  const [strategyId, setStrategyId] = useState('choch_orderblock');
  const [symbol, setSymbol] = useState(activeSymbol);
  const [timeframe, setTimeframe] = useState('5m');
  const [candleCount, setCandleCount] = useState(300);
  const [initialBalance, setInitialBalance] = useState(10000);
  const [spreadPips, setSpreadPips] = useState(2.0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResponse | null>(null);

  if (!isOpen) return null;

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    try {
      const req: BacktestRequest = {
        strategy_id: strategyId,
        symbol: symbol.toUpperCase(),
        timeframe,
        candle_count: candleCount,
        initial_balance: initialBalance,
        risk_pct: 0.01,
        spread_pips: spreadPips,
      };
      const data = await runBacktest(req);
      if (data.ok) {
        setResult(data);
      } else {
        setError(data.error || 'การรัน Backtest ล้มเหลว โปรดตรวจสอบพารามิเตอร์');
      }
    } catch (err: any) {
      setError(err.message || 'เกิดข้อผิดพลาดในการเชื่อมต่อเซิร์ฟเวอร์');
    } finally {
      setLoading(false);
    }
  };

  // Helper to render SVG Equity Curve
  const renderEquityCurve = (curve: number[]) => {
    if (!curve || curve.length < 2) return null;
    const min = Math.min(...curve);
    const max = Math.max(...curve);
    const range = max - min || 1;
    const width = 600;
    const height = 140;
    const pad = 12;

    const points = curve
      .map((val, idx) => {
        const x = pad + (idx / (curve.length - 1)) * (width - pad * 2);
        const y = height - pad - ((val - min) / range) * (height - pad * 2);
        return `${x},${y}`;
      })
      .join(' ');

    const isProfitable = curve[curve.length - 1] >= curve[0];
    const strokeColor = isProfitable ? '#10b981' : '#ef4444';
    const fillColor = isProfitable ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)';

    const firstPoint = points.split(' ')[0];
    const lastPoint = points.split(' ')[points.split(' ').length - 1];
    const closedArea = `${firstPoint} ${points} ${lastPoint.split(',')[0]},${height} ${firstPoint.split(',')[0]},${height}`;

    return (
      <div className="w-full overflow-hidden rounded-xl bg-dark-950/80 border border-dark-800 p-3">
        <div className="flex justify-between items-center mb-1 text-[11px] text-slate-400 font-mono">
          <span>เส้นกราฟการเติบโตของพอร์ต (Equity Curve)</span>
          <span className={isProfitable ? 'text-emerald-400' : 'text-rose-400'}>
            ${curve[0].toLocaleString()} → ${curve[curve.length - 1].toLocaleString()}
          </span>
        </div>
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-32 overflow-visible">
          <polygon points={closedArea} fill={fillColor} />
          <polyline fill="none" stroke={strokeColor} strokeWidth="2.5" points={points} strokeLinecap="round" />
        </svg>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="w-full max-w-4xl max-h-[92vh] flex flex-col bg-dark-900 border border-dark-700/80 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-dark-800 bg-dark-950/70">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-brand-gold/10 border border-brand-gold/30 flex items-center justify-center text-brand-gold">
              <BarChart3 className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white tracking-wide">One-Click Strategy Backtester</h2>
              <p className="text-[11px] text-slate-400">จำลองผลลัพธ์ย้อนหลังด้วยโมเดลสถาบัน SMC & Fee/Slippage เสมือนจริง</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-dark-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Controls Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 p-3.5 bg-dark-950/60 border border-dark-800 rounded-xl text-xs">
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">กลยุทธ์ (Strategy)</label>
              <select
                value={strategyId}
                onChange={(e) => setStrategyId(e.target.value)}
                className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 font-medium text-white focus:outline-none focus:border-brand-gold"
              >
                <option value="choch_orderblock">CHoCH + OB (SMC)</option>
                <option value="breakout_retest">Breakout Retest</option>
                <option value="fvg_reversal">FVG Reversal</option>
                <option value="fvg_optimized">FVG Optimized</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">คู่เหรียญ (Symbol)</label>
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 font-medium text-white focus:outline-none focus:border-brand-gold"
              >
                <option value="BTCUSDT">BTCUSDT</option>
                <option value="ETHUSDT">ETHUSDT</option>
                <option value="SOLUSDT">SOLUSDT</option>
                <option value="BNBUSDT">BNBUSDT</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">Timeframe</label>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 font-medium text-white focus:outline-none focus:border-brand-gold"
              >
                <option value="1m">1m</option>
                <option value="5m">5m (แนะนำ)</option>
                <option value="15m">15m</option>
                <option value="1h">1h</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">จำนวนแท่งเทียน</label>
              <select
                value={candleCount}
                onChange={(e) => setCandleCount(parseInt(e.target.value))}
                className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 font-medium text-white focus:outline-none focus:border-brand-gold"
              >
                <option value="150">150 แท่ง (~12 ชม.)</option>
                <option value="300">300 แท่ง (~24 ชม.)</option>
                <option value="500">500 แท่ง (~42 ชม.)</option>
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-slate-400 mb-1">เงินทุนตั้งต้น ($)</label>
              <input
                type="number"
                step="1000"
                value={initialBalance}
                onChange={(e) => setInitialBalance(parseFloat(e.target.value) || 10000)}
                className="w-full bg-dark-900 border border-dark-700 rounded-lg px-2.5 py-1.5 font-mono text-white focus:outline-none focus:border-brand-gold"
              />
            </div>

            <div className="flex items-end">
              <button
                type="button"
                onClick={handleRun}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-brand-gold hover:bg-brand-gold/90 text-dark-950 font-bold text-xs transition-all shadow-md shadow-brand-gold/10 disabled:opacity-50 cursor-pointer"
              >
                {loading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>กำลังทดสอบ...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>รัน Backtest</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {error && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-300">
              ⚠️ {error}
            </div>
          )}

          {/* Result Display */}
          {result && result.summary && (
            <div className="space-y-4 animate-fade-in">
              {/* Performance Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
                <div className="p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                  <div className="text-[10px] text-slate-400 font-medium">Win Rate</div>
                  <div className={`text-lg font-bold font-mono mt-0.5 ${result.summary.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {result.summary.win_rate}%
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    {result.summary.winners} ชนะ / {result.summary.losers} แพ้
                  </div>
                </div>

                <div className="p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                  <div className="text-[10px] text-slate-400 font-medium">กำไรสุทธิ (Net PnL)</div>
                  <div className={`text-lg font-bold font-mono mt-0.5 ${result.summary.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {result.summary.total_pnl >= 0 ? `+$${result.summary.total_pnl.toFixed(2)}` : `-$${Math.abs(result.summary.total_pnl).toFixed(2)}`}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    ทุนสิ้นสุด: ${result.summary.final_equity.toLocaleString()}
                  </div>
                </div>

                <div className="p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                  <div className="text-[10px] text-slate-400 font-medium">Profit Factor</div>
                  <div className={`text-lg font-bold font-mono mt-0.5 ${result.summary.profit_factor >= 1.5 ? 'text-emerald-400' : (result.summary.profit_factor >= 1.0 ? 'text-amber-400' : 'text-rose-400')}`}>
                    {result.summary.profit_factor.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    {result.summary.profit_factor >= 1.5 ? 'เกณฑ์สถาบันผ่าน' : 'ควรปรับปรุง'}
                  </div>
                </div>

                <div className="p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                  <div className="text-[10px] text-slate-400 font-medium">Max Drawdown</div>
                  <div className={`text-lg font-bold font-mono mt-0.5 ${result.summary.max_drawdown <= 10 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {result.summary.max_drawdown.toFixed(2)}%
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">ต่ำกว่า 10% คือปลอดภัย</div>
                </div>

                <div className="p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                  <div className="text-[10px] text-slate-400 font-medium">Expectancy / Trade</div>
                  <div className="text-lg font-bold font-mono text-cyan-400 mt-0.5">
                    ${result.summary.expectancy.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">ค่าคาดหวังเฉลี่ย</div>
                </div>

                <div className="p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                  <div className="text-[10px] text-slate-400 font-medium">Sharpe Ratio</div>
                  <div className="text-lg font-bold font-mono text-purple-400 mt-0.5">
                    {result.summary.sharpe_ratio.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">ความคุ้มค่าความเสี่ยง</div>
                </div>
              </div>

              {/* Equity Curve */}
              {renderEquityCurve(result.equity_curve)}

              {/* Trade Log Table */}
              <div className="p-4 bg-dark-950/60 border border-dark-800 rounded-xl space-y-3">
                <div className="flex justify-between items-center">
                  <div className="text-xs font-bold text-white">บันทึกการเข้าเทรดจำลอง ({result.trades?.length || 0} รายการ)</div>
                  <div className="text-[11px] text-slate-400">หักค่าธรรมเนียม Taker Fee 0.05% และจำลอง Slippage แล้ว</div>
                </div>

                {(!result.trades || result.trades.length === 0) ? (
                  <div className="text-center py-6 text-xs text-slate-500">
                    ไม่มีออเดอร์ที่เข้าเกณฑ์ในกรอบเวลานี้ (เงื่อนไขความเสี่ยงปลอดภัย Fail-Closed)
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs font-mono">
                      <thead>
                        <tr className="border-b border-dark-800 text-slate-400 text-[10px]">
                          <th className="py-2 px-2">#</th>
                          <th className="py-2 px-2">ฝั่ง (SIDE)</th>
                          <th className="py-2 px-2">ราคาเข้า</th>
                          <th className="py-2 px-2">ราคาออก</th>
                          <th className="py-2 px-2">กำไร/ขาดทุน ($)</th>
                          <th className="py-2 px-2">R-MULTIPLE</th>
                          <th className="py-2 px-2">ผลลัพธ์</th>
                          <th className="py-2 px-2">เวลา</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-dark-800/60">
                        {result.trades.map((t, idx) => (
                          <tr key={idx} className="hover:bg-dark-900/60 transition-colors">
                            <td className="py-2 px-2 text-slate-500">#{t.id || idx + 1}</td>
                            <td className="py-2 px-2">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                t.direction === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                              }`}>
                                {t.direction}
                              </span>
                            </td>
                            <td className="py-2 px-2 text-slate-200">${Number(t.entry).toLocaleString()}</td>
                            <td className="py-2 px-2 text-slate-200">${Number(t.exit).toLocaleString()}</td>
                            <td className={`py-2 px-2 font-bold ${t.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {t.pnl >= 0 ? `+$${Number(t.pnl).toFixed(2)}` : `-$${Math.abs(Number(t.pnl)).toFixed(2)}`}
                            </td>
                            <td className="py-2 px-2 text-cyan-300">
                              {t.r_multiple !== undefined ? `${t.r_multiple > 0 ? '+' : ''}${Number(t.r_multiple).toFixed(1)}R` : '-'}
                            </td>
                            <td className="py-2 px-2">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                t.status === 'WIN' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                              }`}>
                                {t.status}
                              </span>
                            </td>
                            <td className="py-2 px-2 text-slate-400 text-[11px]">{t.time || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

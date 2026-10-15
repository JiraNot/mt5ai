import React, { useState } from 'react';
import {
  ShieldAlert,
  Zap,
  Activity,
  Layers,
  ChevronRight,
  Lock,
  Unlock,
  AlertTriangle,
} from 'lucide-react';
import { StatusResponse, ReadinessData, triggerPanic, setTradingMode } from '../services/api';

interface HeaderProps {
  status: StatusResponse | null;
  readiness: ReadinessData | null;
  lastTick: { bid: number; ask: number; last: number } | null;
  activeSymbol: string;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  status,
  readiness,
  lastTick,
  activeSymbol,
  onRefresh,
}) => {
  const [panicLoading, setPanicLoading] = useState(false);
  const [showPanicModal, setShowPanicModal] = useState(false);
  const [panicResult, setPanicResult] = useState<string | null>(null);

  const handlePanicConfirm = async () => {
    setPanicLoading(true);
    try {
      const res = await triggerPanic();
      setPanicResult(res.message);
      onRefresh();
      setTimeout(() => {
        setShowPanicModal(false);
        setPanicResult(null);
      }, 2500);
    } catch (err: any) {
      alert('Panic failed: ' + err.message);
    } finally {
      setPanicLoading(false);
    }
  };

  const handleToggleMode = async () => {
    if (!status) return;
    const isLive = status.mode.toUpperCase() === 'LIVE';
    if (!isLive) {
      const ok = window.confirm(
        '⚠️ ต้องการเปลี่ยนเป็นโหมด LIVE หรือไม่? (ต้องมั่นใจว่าระบบพร้อมและผ่านเกณฑ์ Promotion Gate)'
      );
      if (ok) {
        await setTradingMode('LIVE', true);
        onRefresh();
      }
    } else {
      await setTradingMode('PAPER', false);
      onRefresh();
    }
  };

  const readinessScore = readiness?.readiness_score ?? 0;
  const isPaper = (status?.mode ?? 'PAPER').toUpperCase() === 'PAPER';

  return (
    <header className="h-14 border-b border-dark-800 bg-dark-900 px-4 flex items-center justify-between z-20">
      {/* Brand & Market Context */}
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-brand-gold to-amber-500 flex items-center justify-center shadow-lg shadow-amber-500/10">
            <Zap className="w-5 h-5 text-dark-950 font-bold" />
          </div>
          <div>
            <div className="flex items-center space-x-1.5">
              <span className="font-bold tracking-wider text-sm text-white">FREEBUFF</span>
              <span className="text-[10px] bg-brand-gold/10 text-brand-gold px-1.5 py-0.5 rounded font-mono font-semibold">
                AI TERMINAL
              </span>
            </div>
            <div className="text-[11px] text-slate-400 font-mono">Binance USDT-M Futures</div>
          </div>
        </div>

        <div className="h-6 w-px bg-dark-800" />

        {/* Symbol Price Flash */}
        <div className="flex items-center space-x-3">
          <span className="font-bold text-sm tracking-wide text-white">{activeSymbol}</span>
          {lastTick ? (
            <div className="font-mono text-sm font-semibold text-brand-green flex items-center space-x-1">
              <span>${lastTick.last.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>
              <span className="text-[10px] text-slate-400">
                (Spread: {((lastTick.ask - lastTick.bid)).toFixed(2)})
              </span>
            </div>
          ) : (
            <div className="text-xs text-slate-500 flex items-center space-x-1">
              <Activity className="w-3.5 h-3.5 animate-pulse text-brand-gold" />
              <span>Connecting feed...</span>
            </div>
          )}
        </div>
      </div>

      {/* Middle Stats & Readiness */}
      <div className="hidden lg:flex items-center space-x-6">
        {/* Account Info */}
        <div className="flex items-center space-x-4 font-mono text-xs">
          <div>
            <span className="text-slate-400 mr-1.5">Balance:</span>
            <span className="font-semibold text-slate-200">
              ${(status?.account?.balance ?? 100000).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>
          <div>
            <span className="text-slate-400 mr-1.5">Equity:</span>
            <span className="font-semibold text-slate-100">
              ${(status?.account?.equity ?? 100000).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>
        </div>

        <div className="h-4 w-px bg-dark-800" />

        {/* Live Promotion Readiness Mini-Gauge */}
        <div className="flex items-center space-x-2 text-xs">
          <span className="text-slate-400">Live Readiness:</span>
          <div className="w-28 bg-dark-800 rounded-full h-2 overflow-hidden relative">
            <div
              className={`h-full transition-all duration-500 ${
                readinessScore >= 80 ? 'bg-brand-green' : readinessScore >= 50 ? 'bg-brand-gold' : 'bg-brand-blue'
              }`}
              style={{ width: `${Math.max(readinessScore, 5)}%` }}
            />
          </div>
          <span className="font-mono text-xs font-bold text-slate-200">{readinessScore}%</span>
        </div>
      </div>

      {/* Right Controls: Mode Toggle + Panic */}
      <div className="flex items-center space-x-3">
        {/* Mode Badge */}
        <button
          onClick={handleToggleMode}
          className={`px-2.5 py-1 rounded text-xs font-semibold font-mono flex items-center space-x-1.5 border transition-colors ${
            isPaper
              ? 'bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/20'
              : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/25'
          }`}
          title="คลิกเพื่อสลับโหมด"
        >
          {isPaper ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3 text-emerald-400" />}
          <span>{status?.mode || 'PAPER'} MODE</span>
        </button>

        {/* Panic Button */}
        <button
          onClick={() => setShowPanicModal(true)}
          className="px-3 py-1.5 rounded bg-brand-red/90 hover:bg-brand-red text-white text-xs font-bold flex items-center space-x-1.5 shadow-md shadow-brand-red/20 transition-all active:scale-95"
        >
          <ShieldAlert className="w-4 h-4" />
          <span>PANIC</span>
        </button>
      </div>

      {/* Panic Confirmation Modal */}
      {showPanicModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-dark-900 border border-brand-red/40 rounded-xl p-6 max-w-md w-full shadow-2xl text-center animate-in fade-in zoom-in-95 duration-150">
            <div className="w-12 h-12 rounded-full bg-brand-red/20 text-brand-red flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-bold text-white mb-2">ยืนยันคำสั่งฉุกเฉิน (PANIC KILL-SWITCH)</h3>
            <p className="text-xs text-slate-300 leading-relaxed mb-6">
              ระบบจะทำการ **ปิดคำสั่งที่เปิดอยู่ทั้งหมดทันทีที่ราคาตลาด** และปลดล็อกความเสี่ยงเพื่อความปลอดภัยสูงสุดของพอร์ต
            </p>

            {panicResult ? (
              <div className="p-3 bg-brand-green/10 border border-brand-green/30 rounded-lg text-brand-green text-xs font-semibold mb-4">
                {panicResult}
              </div>
            ) : (
              <div className="flex space-x-3 justify-center">
                <button
                  onClick={() => setShowPanicModal(false)}
                  disabled={panicLoading}
                  className="px-4 py-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-slate-300 text-xs font-medium transition-colors"
                >
                  ยกเลิก
                </button>
                <button
                  onClick={handlePanicConfirm}
                  disabled={panicLoading}
                  className="px-5 py-2 rounded-lg bg-brand-red hover:bg-brand-redHover text-white text-xs font-bold flex items-center space-x-2 shadow-lg shadow-brand-red/30 transition-all"
                >
                  {panicLoading ? (
                    <span>กำลังปิดทุกออเดอร์...</span>
                  ) : (
                    <>
                      <ShieldAlert className="w-4 h-4" />
                      <span>ปิดทุกไม้ทันที</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
};

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
  Terminal as TerminalIcon,
  Settings as SettingsIcon,
  BarChart3,
  LayoutDashboard,
  Play,
  PanelRight,
  PanelRightClose,
  BookOpen,
} from 'lucide-react';
import { StatusResponse, ReadinessData, triggerPanic, setTradingMode, simulatePaperTrade } from '../services/api';

interface HeaderProps {
  status: StatusResponse | null;
  readiness: ReadinessData | null;
  lastTick: { bid: number; ask: number; last: number } | null;
  activeSymbol: string;
  onRefresh: () => void;
  onToggleSidebar?: () => void;
  isSidebarOpen?: boolean;
  candidatesCount?: number;
  onOpenSettings?: () => void;
  onOpenBacktest?: () => void;
  onOpenGuide?: () => void;
  viewMode?: 'chart' | 'dashboard';
  onToggleViewMode?: (mode: 'chart' | 'dashboard') => void;
}

export const Header: React.FC<HeaderProps> = ({
  status,
  readiness,
  lastTick,
  activeSymbol,
  onRefresh,
  onToggleSidebar,
  isSidebarOpen = true,
  candidatesCount,
  onOpenSettings,
  onOpenBacktest,
  onOpenGuide,
  viewMode = 'chart',
  onToggleViewMode,
}) => {
  const [panicLoading, setPanicLoading] = useState(false);
  const [showPanicModal, setShowPanicModal] = useState(false);
  const [panicResult, setPanicResult] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);

  const handleSimulateTrade = async () => {
    setSimulating(true);
    try {
      await simulatePaperTrade(activeSymbol, 'BUY', 'CHoCH + Order Block');
      onRefresh();
    } catch (err: any) {
      alert('Simulate trade error: ' + err.message);
    } finally {
      setSimulating(false);
    }
  };

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
    <header className="h-14 border-b border-dark-800 bg-dark-900 px-3 sm:px-4 flex items-center justify-between z-20 shrink-0">
      {/* Brand & Market Context */}
      <div className="flex items-center space-x-2.5 sm:space-x-4 shrink-0 whitespace-nowrap">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-brand-gold to-amber-500 flex items-center justify-center shadow-lg shadow-amber-500/10 shrink-0">
            <Zap className="w-5 h-5 text-dark-950 font-bold" />
          </div>
          <div>
            <div className="flex items-center space-x-1.5">
              <span className="font-bold tracking-wider text-sm text-white">APEXTRADER</span>
              <span className="text-[10px] bg-brand-gold/10 text-brand-gold px-1.5 py-0.5 rounded font-mono font-semibold">
                AI TERMINAL
              </span>
            </div>
            <div className="text-[11px] text-slate-400 font-mono hidden xl:block">Binance USDT-M Futures</div>
          </div>
        </div>

        <div className="h-6 w-px bg-dark-800 hidden sm:block" />

        {/* Symbol Price Flash */}
        <div className="flex items-center space-x-2 sm:space-x-3">
          <span className="font-bold text-sm tracking-wide text-white">{activeSymbol}</span>
          {lastTick ? (
            <div className="font-mono text-xs sm:text-sm font-semibold text-brand-green flex items-center space-x-1">
              <span>${lastTick.last.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</span>
              <span className="text-[10px] text-slate-400 hidden xl:inline">
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
      <div className="hidden lg:flex items-center space-x-3 lg:space-x-5 shrink-0 whitespace-nowrap">
        {/* Account Info */}
        <div className="flex items-center space-x-3 lg:space-x-4 font-mono text-xs">
          <div>
            <span className="text-slate-400 mr-1">Bal:</span>
            <span className="font-semibold text-slate-200">
              ${(status?.account?.balance ?? 100000).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>
          <div>
            <span className="text-slate-400 mr-1">Eq:</span>
            <span className="font-semibold text-slate-100">
              ${(status?.account?.equity ?? 100000).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>
        </div>

        {/* Live Promotion Readiness Mini-Gauge (Desktop & Wide Tablet) */}
        <div className="hidden xl:flex items-center space-x-2 text-xs">
          <div className="h-4 w-px bg-dark-800" />
          <span className="text-slate-400">Readiness:</span>
          <div className="w-24 bg-dark-800 rounded-full h-2 overflow-hidden relative">
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

      {/* Right Controls: Mode Toggle + AI Login + Panic + Sidebar Toggle */}
      <div className="flex items-center space-x-2 sm:space-x-2.5 shrink-0 whitespace-nowrap">
        {/* Mode Badge */}
        <button
          onClick={handleToggleMode}
          className={`px-3.5 py-2 rounded-lg text-xs font-semibold font-mono flex items-center space-x-1.5 border min-h-[44px] min-w-[44px] active:scale-95 transition-all ${
            isPaper
              ? 'bg-blue-500/10 border-blue-500/30 text-blue-400 hover:bg-blue-500/20'
              : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/25'
          }`}
          title="คลิกเพื่อสลับโหมด"
        >
          {isPaper ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5 text-emerald-400" />}
          <span>{status?.mode || 'PAPER'}</span>
        </button>

        {/* AI Login & Terminal Button */}
        <a
          href="/terminal"
          target="_blank"
          rel="noopener noreferrer"
          className="hidden sm:flex px-3.5 py-2 rounded-lg text-xs font-semibold font-mono items-center space-x-1.5 border border-purple-500/30 bg-purple-500/10 text-purple-300 hover:bg-purple-500/20 min-h-[44px] min-w-[44px] active:scale-95 transition-all"
          title="เปิดหน้าต่าง Terminal เพื่อ Login ChatGPT / Codex"
        >
          <TerminalIcon className="w-3.5 h-3.5" />
          <span>AI LOGIN</span>
        </a>

        {/* Dynamic Settings Button */}
        {onOpenSettings && (
          <button
            onClick={onOpenSettings}
            className="px-3.5 py-2 rounded-lg text-xs font-semibold font-mono flex items-center space-x-1.5 border border-dark-700 bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 min-h-[44px] min-w-[44px] active:scale-95 transition-all"
            title="เปิดหน้าต่างตั้งค่าระบบ (Risk, Binance API, AI, Telegram)"
          >
            <SettingsIcon className="w-3.5 h-3.5 text-brand-gold" />
            <span className="hidden md:inline">SETTINGS</span>
          </button>
        )}

        {/* One-Click Backtest Button */}
        {onOpenBacktest && (
          <button
            onClick={onOpenBacktest}
            className="px-3.5 py-2 rounded-lg text-xs font-semibold font-mono flex items-center space-x-1.5 border border-dark-700 bg-dark-800 text-slate-300 hover:text-white hover:bg-dark-700 min-h-[44px] min-w-[44px] active:scale-95 transition-all"
            title="เปิดหน้าต่างรัน Backtest จำลองย้อนหลัง"
          >
            <BarChart3 className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden md:inline">BACKTEST</span>
          </button>
        )}

        {/* User Guide Button */}
        {onOpenGuide && (
          <button
            onClick={onOpenGuide}
            className="px-3.5 py-2 rounded-lg text-xs font-semibold font-mono flex items-center space-x-1.5 border border-cyan-500/30 bg-cyan-500/10 text-cyan-300 hover:text-white hover:bg-cyan-500/20 min-h-[44px] min-w-[44px] active:scale-95 transition-all shadow-xs"
            title="เปิดคู่มือการใช้งานและวิธีเชื่อมต่อเงินจริง"
          >
            <BookOpen className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden md:inline font-bold">GUIDE</span>
          </button>
        )}

        {/* View Mode Toggle: Chart vs Institutional Pro Desk */}
        {onToggleViewMode && (
          <div className="flex items-center bg-dark-800/90 border border-dark-700 rounded-lg p-0.5">
            <button
              onClick={() => onToggleViewMode('chart')}
              className={`px-2.5 py-1.5 rounded-md text-xs font-semibold font-mono flex items-center space-x-1 transition-all ${
                viewMode === 'chart'
                  ? 'bg-dark-700 text-cyan-300 shadow-xs border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="สลับเป็นกราฟแท่งเทียน Candlestick Chart"
            >
              <BarChart3 className="w-3.5 h-3.5" />
              <span className="hidden lg:inline">CHART</span>
            </button>
            <button
              onClick={() => onToggleViewMode('dashboard')}
              className={`px-2.5 py-1.5 rounded-md text-xs font-semibold font-mono flex items-center space-x-1 transition-all ${
                viewMode === 'dashboard'
                  ? 'bg-amber-500/20 text-brand-gold border border-brand-gold/50 shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="สลับเป็นหน้า Institutional Prop Desk (SwingFrontRun Dashboard)"
            >
              <LayoutDashboard className="w-3.5 h-3.5 text-brand-gold" />
              <span className="hidden lg:inline">PRO DESK</span>
            </button>
          </div>
        )}

        {/* Simulate Paper Order Button */}
        {isPaper && (
          <button
            onClick={handleSimulateTrade}
            disabled={simulating}
            className="px-3 py-2 rounded-lg text-xs font-semibold font-mono flex items-center space-x-1.5 border border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20 min-h-[44px] min-w-[44px] active:scale-95 transition-all"
            title="จำลองให้ AI เปิดออเดอร์ซ้อมเทรดตามโครงสร้าง SMC ทันที (พร้อม SL/TP ในโหมด Paper)"
          >
            <Play className={`w-3.5 h-3.5 text-emerald-400 ${simulating ? 'animate-spin' : ''}`} />
            <span className="hidden xl:inline">SIMULATE ORDER</span>
          </button>
        )}

        {/* Panic Button */}
        <button
          onClick={() => {
            if (typeof navigator !== 'undefined' && 'vibrate' in navigator) navigator.vibrate(40);
            setShowPanicModal(true);
          }}
          className="px-4 py-2 rounded-lg bg-brand-red/90 hover:bg-brand-red text-white text-xs font-bold flex items-center space-x-1.5 shadow-md shadow-brand-red/20 min-h-[44px] min-w-[44px] active:scale-95 transition-all"
        >
          <ShieldAlert className="w-4 h-4" />
          <span>PANIC</span>
        </button>

        {/* Sidebar Toggle for Tablet/Mobile */}
        {onToggleSidebar && (
          <button
            onClick={onToggleSidebar}
            className={`md:hidden px-3.5 py-2 rounded-lg border text-xs font-semibold flex items-center space-x-1 min-h-[44px] min-w-[44px] active:scale-95 transition-all ${
              isSidebarOpen
                ? 'bg-brand-gold/15 border-brand-gold/40 text-brand-gold'
                : 'bg-dark-800 border-dark-700 text-slate-300'
            }`}
            title="เปิด/ปิด AI Watchlist & Council"
          >
            {isSidebarOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRight className="w-4 h-4" />}
            {candidatesCount !== undefined && candidatesCount > 0 && (
              <span className="bg-brand-gold text-dark-950 px-1 rounded-full text-[10px] font-bold">
                {candidatesCount}
              </span>
            )}
          </button>
        )}
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
                  className="px-4 py-2.5 rounded-lg bg-dark-800 hover:bg-dark-700 text-slate-300 text-xs font-medium transition-colors min-h-[44px] min-w-[44px]"
                >
                  ยกเลิก
                </button>
                <button
                  onClick={handlePanicConfirm}
                  disabled={panicLoading}
                  className="px-5 py-2.5 rounded-lg bg-brand-red hover:bg-brand-redHover text-white text-xs font-bold flex items-center space-x-2 shadow-lg shadow-brand-red/30 transition-all min-h-[44px] min-w-[44px]"
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

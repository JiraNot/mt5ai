import React, { useState } from 'react';
import { Layers, History, Shield, X, ArrowUpRight, ArrowDownRight, ChevronDown, ChevronUp } from 'lucide-react';
import { PositionItem, closePosition, lockBreakEven } from '../services/api';

interface PositionsTableProps {
  positions: PositionItem[];
  history: any[];
  onRefresh: () => void;
}

export const PositionsTable: React.FC<PositionsTableProps> = ({ positions, history, onRefresh }) => {
  const [activeTab, setActiveTab] = useState<'positions' | 'history'>('positions');
  const [loadingAction, setLoadingAction] = useState<number | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleClose = async (ticket: number, symbol: string) => {
    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) navigator.vibrate(40);
    if (!window.confirm(`ต้องการปิดออเดอร์ #${ticket} ทันทีหรือไม่?`)) return;
    setLoadingAction(ticket);
    try {
      await closePosition(ticket, symbol);
      onRefresh();
    } catch (e: any) {
      alert('Close error: ' + e.message);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleBE = async (ticket: number, symbol: string) => {
    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) navigator.vibrate(40);
    setLoadingAction(ticket);
    try {
      await lockBreakEven(ticket, symbol);
      alert('ขยับ Stop Loss บังหน้าทุน (BE) เรียบร้อยแล้ว');
      onRefresh();
    } catch (e: any) {
      alert('BE error: ' + e.message);
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div
      className={`border-t border-dark-800 bg-dark-900/60 flex flex-col overflow-hidden transition-all duration-200 ${
        isCollapsed ? 'h-[52px]' : 'h-48 md:h-56'
      }`}
    >
      {/* Table Header Tabs & Controls */}
      <div className="min-h-[52px] py-1 px-3.5 border-b border-dark-800 flex items-center justify-between bg-dark-900/80 select-none">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => {
              setActiveTab('positions');
              if (isCollapsed) setIsCollapsed(false);
            }}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-all min-h-[44px] min-w-[44px] active:scale-95 ${
              activeTab === 'positions'
                ? 'bg-dark-750 text-white border-b-2 border-brand-gold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Active Positions ({positions.length})</span>
          </button>

          <button
            onClick={() => {
              setActiveTab('history');
              if (isCollapsed) setIsCollapsed(false);
            }}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-all min-h-[44px] min-w-[44px] active:scale-95 ${
              activeTab === 'history'
                ? 'bg-dark-750 text-white border-b-2 border-brand-gold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <History className="w-3.5 h-3.5" />
            <span>Closed History</span>
          </button>
        </div>

        {/* Collapse / Expand Toggle */}
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-dark-800 min-h-[44px] min-w-[44px] flex items-center justify-center transition-colors"
          title={isCollapsed ? 'ขยายตาราง Position' : 'ย่อตารางเพื่อดูกราฟเต็มจอ'}
        >
          {isCollapsed ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {/* Table Content */}
      {!isCollapsed && (
        <div className="flex-1 overflow-x-auto overflow-y-auto">
        {activeTab === 'positions' ? (
          positions.length === 0 ? (
            <div className="h-full flex items-center justify-center text-xs text-slate-500 font-mono">
              ไม่มีไม้ที่ถืออยู่ (No open positions) — AI กำลังเฝ้าจับจังหวะตามโครงสร้างตลาด
            </div>
          ) : (
            <table className="w-full min-w-[800px] text-left font-mono text-xs border-collapse">
              <thead className="sticky top-0 bg-dark-900 text-slate-400 border-b border-dark-800 text-[11px]">
                <tr>
                  <th className="py-2 px-3.5">Ticket</th>
                  <th className="py-2 px-3.5">Symbol</th>
                  <th className="py-2 px-3.5">Side</th>
                  <th className="py-2 px-3.5">Size</th>
                  <th className="py-2 px-3.5">Entry</th>
                  <th className="py-2 px-3.5">Mark Price</th>
                  <th className="py-2 px-3.5">SL</th>
                  <th className="py-2 px-3.5">TP</th>
                  <th className="py-2 px-3.5">PnL ($)</th>
                  <th className="py-2 px-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-800/60">
                {positions.map((p) => {
                  const isBuy = p.direction === 'BUY';
                  const isProfit = p.profit >= 0;

                  return (
                    <tr key={p.ticket} className="hover:bg-dark-800/40 transition-colors">
                      <td className="py-2.5 px-3.5 text-slate-400">#{p.ticket}</td>
                      <td className="py-2.5 px-3.5 font-bold text-white">{p.symbol}</td>
                      <td className="py-2.5 px-3.5">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            isBuy ? 'bg-brand-green/15 text-brand-green' : 'bg-brand-red/15 text-brand-red'
                          }`}
                        >
                          {p.direction}
                        </span>
                      </td>
                      <td className="py-2.5 px-3.5 text-slate-300">{p.volume}</td>
                      <td className="py-2.5 px-3.5 text-slate-300">${p.open_price.toLocaleString()}</td>
                      <td className="py-2.5 px-3.5 text-slate-200">${p.current_price.toLocaleString()}</td>
                      <td className="py-2.5 px-3.5 text-brand-red">${p.sl > 0 ? p.sl.toLocaleString() : '-'}</td>
                      <td className="py-2.5 px-3.5 text-brand-green">${p.tp > 0 ? p.tp.toLocaleString() : '-'}</td>
                      <td className={`py-2.5 px-3.5 font-semibold ${isProfit ? 'text-brand-green' : 'text-brand-red'}`}>
                        {isProfit ? '+' : ''}${p.profit.toFixed(2)} ({isProfit ? '+' : ''}{p.pnl_pct.toFixed(2)}%)
                      </td>
                      <td className="py-2.5 px-3.5 text-right">
                        <div className="flex items-center justify-end space-x-2">
                          <button
                            onClick={() => handleBE(p.ticket, p.symbol)}
                            disabled={loadingAction === p.ticket}
                            className="px-3.5 py-2 rounded-lg bg-blue-500/15 text-blue-400 hover:bg-blue-500/25 border border-blue-500/30 text-xs font-semibold flex items-center space-x-1.5 min-h-[44px] min-w-[44px] active:scale-95 transition-all"
                            title="ขยับ Stop Loss บังหน้าทุนทันที"
                          >
                            <Shield className="w-3.5 h-3.5" />
                            <span>Lock BE</span>
                          </button>
                          <button
                            onClick={() => handleClose(p.ticket, p.symbol)}
                            disabled={loadingAction === p.ticket}
                            className="px-3.5 py-2 rounded-lg bg-brand-red/15 text-brand-red hover:bg-brand-red/25 border border-brand-red/30 text-xs font-semibold flex items-center space-x-1.5 min-h-[44px] min-w-[44px] active:scale-95 transition-all"
                            title="ปิดออเดอร์นี้ทันที"
                          >
                            <X className="w-3.5 h-3.5" />
                            <span>Close</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )
        ) : (
          <table className="w-full min-w-[800px] text-left font-mono text-xs border-collapse">
            <thead className="sticky top-0 bg-dark-900 text-slate-400 border-b border-dark-800 text-[11px]">
              <tr>
                <th className="py-2 px-3.5">Symbol</th>
                <th className="py-2 px-3.5">Side</th>
                <th className="py-2 px-3.5">Size</th>
                <th className="py-2 px-3.5">Entry</th>
                <th className="py-2 px-3.5">Exit</th>
                <th className="py-2 px-3.5">Net PnL</th>
                <th className="py-2 px-3.5">R-Multiple</th>
                <th className="py-2 px-3.5">Exit Reason</th>
                <th className="py-2 px-3.5">Exit Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dark-800/60">
              {history.map((t) => (
                <tr key={t.id} className="hover:bg-dark-800/40 transition-colors">
                  <td className="py-2.5 px-3.5 font-bold text-white">{t.symbol}</td>
                  <td className="py-2.5 px-3.5">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        t.direction === 'BUY' ? 'bg-brand-green/15 text-brand-green' : 'bg-brand-red/15 text-brand-red'
                      }`}
                    >
                      {t.direction}
                    </span>
                  </td>
                  <td className="py-2.5 px-3.5 text-slate-300">{t.volume}</td>
                  <td className="py-2.5 px-3.5 text-slate-300">${t.entry_price?.toLocaleString()}</td>
                  <td className="py-2.5 px-3.5 text-slate-300">${t.exit_price?.toLocaleString()}</td>
                  <td className={`py-2.5 px-3.5 font-semibold ${t.profit >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
                    {t.profit >= 0 ? '+' : ''}${t.profit?.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-3.5 text-brand-gold font-bold">{t.r_multiple?.toFixed(2)}R</td>
                  <td className="py-2.5 px-3.5 text-slate-400 text-[11px]">{t.exit_reason || 'Target Met'}</td>
                  <td className="py-2.5 px-3.5 text-slate-400 text-[11px]">
                    {t.exit_time ? new Date(t.exit_time).toLocaleTimeString() : '-'}
                  </td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-6 text-center text-slate-500 text-xs">
                    ยังไม่มีประวัติการปิดไม้
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        </div>
      )}
    </div>
  );
};

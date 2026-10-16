import React, { useState } from 'react';
import { Sparkles, TrendingUp, TrendingDown, RefreshCw, Compass, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { WatchlistData, triggerScan } from '../services/api';

interface WatchlistPanelProps {
  data: WatchlistData | null;
  activeSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  onRefresh: () => void;
}

export const WatchlistPanel: React.FC<WatchlistPanelProps> = ({
  data,
  activeSymbol,
  onSelectSymbol,
  onRefresh,
}) => {
  const [scanning, setScanning] = useState(false);

  const handleScan = async () => {
    setScanning(true);
    try {
      await triggerScan();
      setTimeout(() => {
        onRefresh();
        setScanning(false);
      }, 3000);
    } catch (e: any) {
      alert('Scan error: ' + e.message);
      setScanning(false);
    }
  };

  const btc = data?.btc_report;
  const candidates = data?.candidates || [];

  return (
    <div className="w-full h-full border-b border-dark-800 bg-dark-900/40 flex flex-col overflow-hidden">
      {/* Panel Header */}
      <div className="min-h-[52px] py-1 px-3.5 border-b border-dark-800 flex items-center justify-between bg-dark-900/70 select-none">
        <div className="flex items-center space-x-2">
          <Compass className="w-4 h-4 text-brand-gold" />
          <span className="text-xs font-bold tracking-wider text-slate-200">AI WATCHLIST</span>
        </div>
        <button
          onClick={handleScan}
          disabled={scanning}
          className="px-3.5 py-2 rounded-lg bg-brand-gold/10 hover:bg-brand-gold/20 active:scale-95 text-brand-gold text-xs font-semibold flex items-center space-x-1.5 border border-brand-gold/30 transition-all min-h-[44px] min-w-[44px]"
          title="บังคับ AI สแกนคัดเหรียญทันที"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
          <span>{scanning ? 'Scanning...' : 'Scan Now'}</span>
        </button>
      </div>

      {/* BTC Macro Regime Insight Card */}
      {btc && (
        <div className="p-3 border-b border-dark-800 bg-dark-900/80">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center space-x-1.5">
              <span className="font-bold text-xs text-white">BTC Macro Bias</span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded font-semibold uppercase ${
                  btc.trend_direction === 'BUY'
                    ? 'bg-brand-green/15 text-brand-green border border-brand-green/30'
                    : 'bg-brand-red/15 text-brand-red border border-brand-red/30'
                }`}
              >
                {btc.regime.replace('_', ' ')}
              </span>
            </div>
          </div>
          <p className="text-[11px] text-slate-300 leading-snug line-clamp-2">
            {btc.recommendation_th}
          </p>
        </div>
      )}

      {/* Candidate List */}
      <div className="flex-1 overflow-y-auto divide-y divide-dark-800/60">
        {candidates.map((coin) => {
          const isActive = coin.symbol === activeSymbol;
          const isUp = coin.price_change_pct >= 0;

          return (
            <div
              key={coin.symbol}
              onClick={() => onSelectSymbol(coin.symbol)}
              className={`p-3.5 cursor-pointer transition-colors active:bg-dark-750 flex items-center justify-between min-h-[52px] ${
                isActive
                  ? 'bg-dark-800/90 border-l-4 border-brand-gold'
                  : 'hover:bg-dark-800/40'
              }`}
            >
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-xs text-white tracking-wide">{coin.symbol}</span>
                  {coin.tags && coin.tags[0] && (
                    <span className="text-[9px] bg-dark-700 text-slate-300 px-1 rounded font-mono">
                      {coin.tags[0]}
                    </span>
                  )}
                </div>
                <div className="text-[11px] font-mono text-slate-400 mt-0.5">
                  ${coin.price ? coin.price.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}
                </div>
              </div>

              <div className="text-right">
                <div
                  className={`text-xs font-mono font-semibold flex items-center justify-end space-x-0.5 ${
                    isUp ? 'text-brand-green' : 'text-brand-red'
                  }`}
                >
                  {isUp ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                  <span>{isUp ? '+' : ''}{coin.price_change_pct.toFixed(2)}%</span>
                </div>
                <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                  Score: <span className="text-brand-gold font-bold">{coin.score.toFixed(0)}</span>
                </div>
              </div>
            </div>
          );
        })}

        {candidates.length === 0 && (
          <div className="p-6 text-center text-xs text-slate-500">
            ยังไม่มีข้อมูล Watchlist กรุณากดปุ่ม Scan Now ด้านบน
          </div>
        )}
      </div>
    </div>
  );
};

import React, { useEffect, useState, useCallback } from 'react';
import { Compass, Bot, X } from 'lucide-react';
import { Header } from './components/Header';
import { TradingChart } from './components/TradingChart';
import { WatchlistPanel } from './components/WatchlistPanel';
import { AICouncilCard } from './components/AICouncilCard';
import { PositionsTable } from './components/PositionsTable';
import { SettingsModal } from './components/SettingsModal';
import {
  fetchStatus,
  fetchWatchlist,
  fetchReadiness,
  fetchPositions,
  fetchCouncilLatest,
  fetchTradeHistory,
  StatusResponse,
  WatchlistData,
  ReadinessData,
  PositionItem,
  CouncilLatest,
} from './services/api';
import { wsClient } from './services/websocket';

export const App: React.FC = () => {
  const [activeSymbol, setActiveSymbol] = useState('BTCUSDT');
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistData | null>(null);
  const [readiness, setReadiness] = useState<ReadinessData | null>(null);
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [council, setCouncil] = useState<CouncilLatest | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [lastTick, setLastTick] = useState<{ bid: number; ask: number; last: number; timestamp: number } | null>(null);
  const [alertBanner, setAlertBanner] = useState<{ level: string; message: string } | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.innerWidth >= 1200;
    }
    return true;
  });
  const [sidebarTab, setSidebarTab] = useState<'watchlist' | 'council'>('watchlist');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // Load all initial state
  const loadAllData = useCallback(async () => {
    try {
      const [sRes, wRes, rRes, pRes, cRes, hRes] = await Promise.allSettled([
        fetchStatus(),
        fetchWatchlist(),
        fetchReadiness(),
        fetchPositions(),
        fetchCouncilLatest(),
        fetchTradeHistory(20),
      ]);

      if (sRes.status === 'fulfilled') setStatus(sRes.value);
      if (wRes.status === 'fulfilled' && wRes.value.ok) setWatchlist(wRes.value.data);
      if (rRes.status === 'fulfilled') setReadiness(rRes.value);
      if (pRes.status === 'fulfilled' && pRes.value.ok) setPositions(pRes.value.positions);
      if (cRes.status === 'fulfilled') setCouncil(cRes.value);
      if (hRes.status === 'fulfilled' && hRes.value.ok) setHistory(hRes.value.trades);
    } catch (e) {
      console.error('Error fetching dashboard state', e);
    }
  }, []);

  // Set up WebSocket listeners
  useEffect(() => {
    loadAllData();

    // Listen to real-time tick
    const unsubTick = wsClient.on('tick', (data) => {
      if (data.symbol === activeSymbol) {
        setLastTick({
          bid: data.bid,
          ask: data.ask,
          last: data.last,
          timestamp: data.timestamp,
        });
      }
    });

    // Listen to positions update
    const unsubPos = wsClient.on('positions', (data) => {
      if (data.positions) {
        setPositions(data.positions);
      }
    });

    // Listen to alerts (panic, scan)
    const unsubAlert = wsClient.on('alert', (data) => {
      setAlertBanner({ level: data.level, message: data.message });
      setTimeout(() => setAlertBanner(null), 5000);
      loadAllData();
    });

    // Periodic poll every 5s for background safety sync
    const interval = setInterval(loadAllData, 5000);

    return () => {
      unsubTick();
      unsubPos();
      unsubAlert();
      clearInterval(interval);
    };
  }, [activeSymbol, loadAllData]);

  // Handle symbol change from Watchlist
  const handleSelectSymbol = (symbol: string) => {
    setActiveSymbol(symbol);
    wsClient.setSymbol(symbol);
    setLastTick(null);
    // On small mobile (< 768px), auto-collapse sidebar to show chart immediately
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  };

  const handleToggleSidebar = () => {
    setIsSidebarOpen((prev) => !prev);
  };

  return (
    <div className="h-screen h-[100dvh] w-screen flex flex-col bg-dark-950 overflow-hidden font-sans select-none">
      {/* Alert Banner */}
      {alertBanner && (
        <div
          className={`py-1.5 px-4 text-xs font-semibold text-center z-50 flex items-center justify-center space-x-2 transition-all ${
            alertBanner.level === 'error'
              ? 'bg-brand-red text-white'
              : 'bg-brand-green text-dark-950 font-bold'
          }`}
        >
          <span>{alertBanner.message}</span>
        </div>
      )}

      {/* Top Header */}
      <Header
        status={status}
        readiness={readiness}
        lastTick={lastTick}
        activeSymbol={activeSymbol}
        onRefresh={loadAllData}
        onToggleSidebar={handleToggleSidebar}
        isSidebarOpen={isSidebarOpen}
        candidatesCount={watchlist?.candidates?.length}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      {/* Main Trading Area */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left/Center: TradingView Candlestick Chart */}
        <TradingChart
          symbol={activeSymbol}
          positions={positions}
          lastTick={lastTick}
          onToggleSidebar={handleToggleSidebar}
          isSidebarOpen={isSidebarOpen}
        />

        {/* Mobile/Tablet Backdrop Overlay */}
        {isSidebarOpen && (
          <div
            className="lg:hidden fixed inset-0 bg-black/60 backdrop-blur-xs z-30 transition-opacity"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}

        {/* Right Sidebar: AI Watchlist + AI Council Verdict */}
        <div
          className={`
            fixed lg:static top-14 bottom-0 right-0 z-40 lg:z-auto
            w-80 md:w-84 max-w-[85vw] flex flex-col bg-dark-900 border-l border-dark-800 shadow-2xl lg:shadow-none
            transition-all duration-200 ease-in-out
            ${isSidebarOpen ? 'translate-x-0' : 'translate-x-full lg:hidden'}
          `}
        >
          {/* Sidebar Tabs (comfortable thumb navigation on tablet & desktop) */}
          <div className="min-h-[52px] py-1 px-3 bg-dark-900/90 border-b border-dark-800 flex items-center justify-between select-none shrink-0">
            <div className="flex items-center space-x-1.5">
              <button
                onClick={() => setSidebarTab('watchlist')}
                className={`px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center space-x-1.5 min-h-[44px] min-w-[44px] transition-all active:scale-95 ${
                  sidebarTab === 'watchlist'
                    ? 'bg-dark-750 text-brand-gold border-b-2 border-brand-gold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Compass className="w-3.5 h-3.5" />
                <span>Watchlist</span>
                {watchlist?.candidates && watchlist.candidates.length > 0 && (
                  <span className="text-[10px] bg-dark-700 text-brand-gold px-1.5 py-0.2 rounded-full font-mono">
                    {watchlist.candidates.length}
                  </span>
                )}
              </button>
              <button
                onClick={() => setSidebarTab('council')}
                className={`px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center space-x-1.5 min-h-[44px] min-w-[44px] transition-all active:scale-95 ${
                  sidebarTab === 'council'
                    ? 'bg-dark-750 text-brand-blue border-b-2 border-brand-blue'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Bot className="w-3.5 h-3.5" />
                <span>AI Council</span>
                {council?.latest && (
                  <span className="text-[10px] bg-dark-700 text-brand-blue px-1.5 py-0.2 rounded-full font-mono">
                    {council.latest.score}
                  </span>
                )}
              </button>
            </div>
            <button
              onClick={() => setIsSidebarOpen(false)}
              className="lg:hidden p-2 rounded-lg text-slate-400 hover:text-white hover:bg-dark-800 min-h-[44px] min-w-[44px] flex items-center justify-center transition-colors"
              title="ปิดแถบข้าง"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Active Tab View */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {sidebarTab === 'watchlist' ? (
              <WatchlistPanel
                data={watchlist}
                activeSymbol={activeSymbol}
                onSelectSymbol={handleSelectSymbol}
                onRefresh={loadAllData}
              />
            ) : (
              <AICouncilCard data={council} />
            )}
          </div>
        </div>
      </div>

      {/* Bottom Positions & Order History Table */}
      <PositionsTable
        positions={positions}
        history={history}
        onRefresh={loadAllData}
      />

      {/* Dynamic Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onSaved={loadAllData}
      />
    </div>
  );
};

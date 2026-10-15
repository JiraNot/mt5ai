import React, { useEffect, useState, useCallback } from 'react';
import { Header } from './components/Header';
import { TradingChart } from './components/TradingChart';
import { WatchlistPanel } from './components/WatchlistPanel';
import { AICouncilCard } from './components/AICouncilCard';
import { PositionsTable } from './components/PositionsTable';
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
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-dark-950 overflow-hidden font-sans select-none">
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
      />

      {/* Main Trading Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left/Center: TradingView Candlestick Chart */}
        <TradingChart
          symbol={activeSymbol}
          positions={positions}
          lastTick={lastTick}
        />

        {/* Right Sidebar: AI Watchlist + AI Council Verdict */}
        <div className="w-80 flex flex-col bg-dark-900/40 border-l border-dark-800">
          <WatchlistPanel
            data={watchlist}
            activeSymbol={activeSymbol}
            onSelectSymbol={handleSelectSymbol}
            onRefresh={loadAllData}
          />
          <AICouncilCard data={council} />
        </div>
      </div>

      {/* Bottom Positions & Order History Table */}
      <PositionsTable
        positions={positions}
        history={history}
        onRefresh={loadAllData}
      />
    </div>
  );
};

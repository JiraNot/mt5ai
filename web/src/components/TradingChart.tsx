import React, { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickData, Time } from 'lightweight-charts';
import {
  PanelRightClose,
  PanelRightOpen,
  TrendingUp,
  SlidersHorizontal,
  BookmarkCheck,
  ListOrdered,
  ChevronDown,
  ChevronUp,
  Crosshair,
  Sparkles,
} from 'lucide-react';
import { fetchCandles, fetchTradeMarkers, CandleItem, PositionItem, TradeMarkerItem, TradeDetailItem } from '../services/api';

interface TradingChartProps {
  symbol: string;
  positions: PositionItem[];
  lastTick: { bid: number; ask: number; last: number; timestamp: number } | null;
  onToggleSidebar?: () => void;
  isSidebarOpen?: boolean;
}

const TIMEFRAMES = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1h', value: '1h' },
  { label: '4h', value: '4h' },
  { label: '1d', value: '1d' },
];

function calculateEMA(candles: CandleItem[], period: number) {
  if (candles.length === 0) return [];
  const k = 2 / (period + 1);
  let ema = candles[0].close;
  return candles.map((c, i) => {
    if (i === 0) ema = c.close;
    else ema = c.close * k + ema * (1 - k);
    return { time: c.time as Time, value: Number(ema.toFixed(4)) };
  });
}

export const TradingChart: React.FC<TradingChartProps> = ({
  symbol,
  positions,
  lastTick,
  onToggleSidebar,
  isSidebarOpen = true,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  // Indicator Series Refs
  const ema20SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ema50SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ema200SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const priceLinesRef = useRef<any[]>([]);
  const srLinesRef = useRef<any[]>([]);

  // State
  const [timeframe, setTimeframe] = useState('5m');
  const [loading, setLoading] = useState(true);
  const [candles, setCandles] = useState<CandleItem[]>([]);

  // Toggle Features
  const [showEMA, setShowEMA] = useState(true);
  const [showSR, setShowSR] = useState(true);
  const [showMarkers, setShowMarkers] = useState(true);
  const [showTradeLog, setShowTradeLog] = useState(false);

  // Trade Markers & Analysis Details
  const [tradeMarkers, setTradeMarkers] = useState<TradeMarkerItem[]>([]);
  const [tradeDetails, setTradeDetails] = useState<TradeDetailItem[]>([]);
  const [selectedTrade, setSelectedTrade] = useState<TradeDetailItem | null>(null);

  // Current Indicator Values for Legend
  const [indicatorValues, setIndicatorValues] = useState<{
    ema20?: number;
    ema50?: number;
    ema200?: number;
    resistance?: number;
    support?: number;
  }>({});

  // 1. Initialize Lightweight Chart & Indicator Series
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#07090e' },
        textColor: '#848e9c',
      },
      grid: {
        vertLines: { color: '#131926' },
        horzLines: { color: '#131926' },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: '#2b3648', labelBackgroundColor: '#1e2638' },
        horzLine: { color: '#2b3648', labelBackgroundColor: '#1e2638' },
      },
      timeScale: {
        borderColor: '#1e2638',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#1e2638',
        autoScale: true,
      },
      handleScale: {
        pinch: true,
        axisPressedMouseMove: true,
        mouseWheel: true,
      },
      handleScroll: {
        vertTouchDrag: false,
        horzTouchDrag: true,
        mouseWheel: true,
        pressedMouseMove: true,
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#0ecb81',
      downColor: '#f6465d',
      borderVisible: false,
      wickUpColor: '#0ecb81',
      wickDownColor: '#f6465d',
    });

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    // EMA 20 (Cyan)
    const ema20 = chart.addLineSeries({
      color: '#00d4ff',
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      title: 'EMA 20',
    });

    // EMA 50 (Amber)
    const ema50 = chart.addLineSeries({
      color: '#f59e0b',
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      title: 'EMA 50',
    });

    // EMA 200 (Purple)
    const ema200 = chart.addLineSeries({
      color: '#a855f7',
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      title: 'EMA 200',
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    ema20SeriesRef.current = ema20;
    ema50SeriesRef.current = ema50;
    ema200SeriesRef.current = ema200;

    const resizeObserver = new ResizeObserver((entries) => {
      if (entries[0] && chartRef.current) {
        const { width, height } = entries[0].contentRect;
        chartRef.current.applyOptions({ width, height });
      }
    });

    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  // 2. Fetch Candles & Calculate Indicators
  useEffect(() => {
    let isCancelled = false;
    setLoading(true);

    const loadData = async () => {
      try {
        const res = await fetchCandles(symbol, timeframe, 300);
        if (isCancelled || !res.ok) return;

        setCandles(res.candles);

        if (candleSeriesRef.current && volumeSeriesRef.current) {
          const chartCandles: CandlestickData<Time>[] = res.candles.map((c) => ({
            time: c.time as Time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
          }));

          const chartVolumes = res.candles.map((c) => ({
            time: c.time as Time,
            value: c.volume,
            color: c.close >= c.open ? 'rgba(14, 203, 129, 0.25)' : 'rgba(246, 70, 93, 0.25)',
          }));

          candleSeriesRef.current.setData(chartCandles);
          volumeSeriesRef.current.setData(chartVolumes);

          // Calculate EMAs
          if (res.candles.length > 0) {
            const ema20Data = calculateEMA(res.candles, 20);
            const ema50Data = calculateEMA(res.candles, 50);
            const ema200Data = calculateEMA(res.candles, 200);

            if (showEMA) {
              ema20SeriesRef.current?.setData(ema20Data);
              ema50SeriesRef.current?.setData(ema50Data);
              ema200SeriesRef.current?.setData(ema200Data);
            } else {
              ema20SeriesRef.current?.setData([]);
              ema50SeriesRef.current?.setData([]);
              ema200SeriesRef.current?.setData([]);
            }

            // Calculate High / Low (S/R)
            const recentHigh = Math.max(...res.candles.slice(-100).map((c) => c.high));
            const recentLow = Math.min(...res.candles.slice(-100).map((c) => c.low));

            setIndicatorValues({
              ema20: ema20Data.length > 0 ? ema20Data[ema20Data.length - 1].value : undefined,
              ema50: ema50Data.length > 0 ? ema50Data[ema50Data.length - 1].value : undefined,
              ema200: ema200Data.length > 0 ? ema200Data[ema200Data.length - 1].value : undefined,
              resistance: recentHigh,
              support: recentLow,
            });
          }

          chartRef.current?.timeScale().fitContent();
        }
      } catch (err) {
        console.error('Error loading candles', err);
      } finally {
        if (!isCancelled) setLoading(false);
      }
    };

    loadData();

    return () => {
      isCancelled = true;
    };
  }, [symbol, timeframe, showEMA]);

  // 3. Support & Resistance Overlays
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    srLinesRef.current.forEach((line) => {
      try {
        candleSeriesRef.current?.removePriceLine(line);
      } catch (e) {}
    });
    srLinesRef.current = [];

    if (!showSR || candles.length === 0) return;

    const recentCandles = candles.slice(-120);
    const resPrice = Math.max(...recentCandles.map((c) => c.high));
    const supPrice = Math.min(...recentCandles.map((c) => c.low));
    const pivotPrice = (resPrice + supPrice) / 2;

    const resLine = candleSeriesRef.current.createPriceLine({
      price: resPrice,
      color: '#ef4444',
      lineWidth: 2,
      lineStyle: 2,
      axisLabelVisible: true,
      title: 'RESISTANCE (SMC)',
    });
    if (resLine) srLinesRef.current.push(resLine);

    const supLine = candleSeriesRef.current.createPriceLine({
      price: supPrice,
      color: '#10b981',
      lineWidth: 2,
      lineStyle: 2,
      axisLabelVisible: true,
      title: 'SUPPORT (SMC)',
    });
    if (supLine) srLinesRef.current.push(supLine);

    const pivotLine = candleSeriesRef.current.createPriceLine({
      price: pivotPrice,
      color: '#3b82f6',
      lineWidth: 1,
      lineStyle: 1,
      axisLabelVisible: false,
      title: 'MID / PIVOT',
    });
    if (pivotLine) srLinesRef.current.push(pivotLine);
  }, [candles, showSR]);

  // 4. Fetch Trade Markers & Details
  useEffect(() => {
    let isCancelled = false;
    fetchTradeMarkers(symbol)
      .then((res) => {
        if (isCancelled || !res.ok) return;
        setTradeMarkers(res.markers);
        setTradeDetails(res.trades);
      })
      .catch((err) => console.error('Failed fetching trade markers', err));

    return () => {
      isCancelled = true;
    };
  }, [symbol]);

  // 5. Apply Trade Markers to Chart
  useEffect(() => {
    if (!candleSeriesRef.current || candles.length === 0) return;

    if (!showMarkers || tradeMarkers.length === 0) {
      candleSeriesRef.current.setMarkers([]);
      return;
    }

    // Filter and snap markers to candles available on the chart
    const candleTimes = new Set(candles.map((c) => c.time));
    const minCandleTime = candles[0].time;
    const maxCandleTime = candles[candles.length - 1].time;

    const validMarkers = tradeMarkers
      .filter((m) => m.time >= minCandleTime && m.time <= maxCandleTime)
      .map((m) => {
        // Snap to nearest candle time if exact bar is missing
        let matchedTime = m.time;
        if (!candleTimes.has(m.time)) {
          let closest = candles[0].time;
          let minDiff = Math.abs(closest - m.time);
          for (const c of candles) {
            const diff = Math.abs(c.time - m.time);
            if (diff < minDiff) {
              minDiff = diff;
              closest = c.time;
            }
          }
          matchedTime = closest;
        }
        return {
          time: matchedTime as Time,
          position: m.position,
          color: m.color,
          shape: m.shape,
          text: m.text,
        };
      })
      .sort((a, b) => (a.time as number) - (b.time as number));

    candleSeriesRef.current.setMarkers(validMarkers);
  }, [tradeMarkers, showMarkers, candles]);

  // 6. Real-time Tick Updates
  useEffect(() => {
    if (!lastTick || !candleSeriesRef.current || candles.length === 0) return;

    const lastCandle = candles[candles.length - 1];
    const newPrice = lastTick.last;

    const updatedCandle: CandlestickData<Time> = {
      time: lastCandle.time as Time,
      open: lastCandle.open,
      high: Math.max(lastCandle.high, newPrice),
      low: Math.min(lastCandle.low, newPrice),
      close: newPrice,
    };

    candleSeriesRef.current.update(updatedCandle);
  }, [lastTick]);

  // 7. Active Positions Overlay (Entry, SL, TP)
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    priceLinesRef.current.forEach((line) => {
      try {
        candleSeriesRef.current?.removePriceLine(line);
      } catch (e) {}
    });
    priceLinesRef.current = [];

    const activePositions = positions.filter((p) => p.symbol === symbol);

    activePositions.forEach((pos) => {
      const entryLine = candleSeriesRef.current?.createPriceLine({
        price: pos.open_price,
        color: '#1e88e5',
        lineWidth: 2,
        lineStyle: 0,
        axisLabelVisible: true,
        title: `ENTRY #${pos.ticket}`,
      });
      if (entryLine) priceLinesRef.current.push(entryLine);

      if (pos.sl > 0) {
        const slLine = candleSeriesRef.current?.createPriceLine({
          price: pos.sl,
          color: '#f6465d',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `SL`,
        });
        if (slLine) priceLinesRef.current.push(slLine);
      }

      if (pos.tp > 0) {
        const tpLine = candleSeriesRef.current?.createPriceLine({
          price: pos.tp,
          color: '#0ecb81',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `TP`,
        });
        if (tpLine) priceLinesRef.current.push(tpLine);
      }
    });
  }, [positions, symbol]);

  return (
    <div className="flex-1 flex flex-col bg-dark-950 relative overflow-hidden border-r border-dark-800">
      {/* Top Bar: Symbol Info, Timeframe Selectors, Indicator Toggles */}
      <div className="min-h-[52px] py-1.5 border-b border-dark-800 px-3.5 flex flex-wrap items-center justify-between bg-dark-900/70 select-none gap-2">
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2">
            <span className="font-bold text-xs sm:text-sm text-white tracking-wider">{symbol}</span>
            <span className="text-[10px] bg-dark-800 text-slate-400 px-1.5 py-0.5 rounded font-mono">PERP</span>
          </div>

          {/* Timeframe Buttons */}
          <div className="flex items-center space-x-1 bg-dark-900/90 p-0.5 rounded-lg border border-dark-800">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.value}
                onClick={() => setTimeframe(tf.value)}
                className={`min-h-[36px] min-w-[36px] px-2 py-1 rounded-md text-xs font-mono font-semibold transition-all flex items-center justify-center active:scale-95 ${
                  timeframe === tf.value
                    ? 'bg-dark-700 text-brand-gold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800/60'
                }`}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>

        {/* Indicator Toggles & Tools Bar */}
        <div className="flex items-center space-x-1.5 sm:space-x-2 flex-wrap">
          {/* EMA Toggle */}
          <button
            onClick={() => setShowEMA(!showEMA)}
            className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold flex items-center space-x-1.5 transition-all active:scale-95 ${
              showEMA
                ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-300'
                : 'bg-dark-900 border-dark-700 text-slate-400 hover:text-slate-200'
            }`}
            title="เปิด/ปิดเส้นค่าเฉลี่ย EMA 20, 50, 200"
          >
            <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">EMA 20/50/200</span>
            <span className="sm:hidden">EMA</span>
          </button>

          {/* S/R Levels Toggle */}
          <button
            onClick={() => setShowSR(!showSR)}
            className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold flex items-center space-x-1.5 transition-all active:scale-95 ${
              showSR
                ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                : 'bg-dark-900 border-dark-700 text-slate-400 hover:text-slate-200'
            }`}
            title="เปิด/ปิดเส้นแนวรับ-แนวต้านอัตโนมัติ"
          >
            <Crosshair className="w-3.5 h-3.5 text-emerald-400" />
            <span className="hidden sm:inline">แนวรับ-ต้าน S/R</span>
            <span className="sm:hidden">S/R</span>
          </button>

          {/* Trade Markers Toggle */}
          <button
            onClick={() => setShowMarkers(!showMarkers)}
            className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold flex items-center space-x-1.5 transition-all active:scale-95 ${
              showMarkers
                ? 'bg-brand-gold/15 border-brand-gold/40 text-brand-gold'
                : 'bg-dark-900 border-dark-700 text-slate-400 hover:text-slate-200'
            }`}
            title="แสดงจุดเข้า-ออกออเดอร์บนแท่งเทียน"
          >
            <BookmarkCheck className="w-3.5 h-3.5 text-brand-gold" />
            <span className="hidden sm:inline">จุดเข้าเทรด</span>
            <span className="sm:hidden">มาร์คจุด</span>
          </button>

          {/* Trade Log Drawer Toggle */}
          <button
            onClick={() => setShowTradeLog(!showTradeLog)}
            className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold flex items-center space-x-1.5 transition-all active:scale-95 ${
              showTradeLog
                ? 'bg-purple-500/15 border-purple-500/40 text-purple-300'
                : 'bg-dark-900 border-dark-700 text-slate-400 hover:text-slate-200'
            }`}
            title="เปิดบันทึกวิเคราะห์เหตุผลการเข้าและผลลัพธ์ของออเดอร์"
          >
            <ListOrdered className="w-3.5 h-3.5 text-purple-400" />
            <span className="hidden sm:inline">วิเคราะห์ออเดอร์ ({tradeDetails.length})</span>
            <span className="sm:hidden">({tradeDetails.length})</span>
            {showTradeLog ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
          </button>

          {/* Sidebar Toggle for Tablet/Desktop */}
          {onToggleSidebar && (
            <button
              onClick={onToggleSidebar}
              className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold flex items-center space-x-1.5 transition-all active:scale-95 ${
                isSidebarOpen
                  ? 'bg-brand-gold/15 border-brand-gold/40 text-brand-gold'
                  : 'bg-dark-800 border-dark-700 text-slate-300 hover:text-white'
              }`}
            >
              {isSidebarOpen ? <PanelRightClose className="w-3.5 h-3.5" /> : <PanelRightOpen className="w-3.5 h-3.5" />}
              <span className="hidden lg:inline">{isSidebarOpen ? 'Hide Panel' : 'Panel'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Dynamic Indicators Value Strip */}
      {showEMA && (
        <div className="bg-dark-950/90 border-b border-dark-800 px-3.5 py-1 flex items-center space-x-4 text-[11px] font-mono overflow-x-auto select-none">
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-[#00d4ff]" />
            <span className="text-slate-400">EMA20:</span>
            <span className="text-cyan-300 font-semibold">{indicatorValues.ema20?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '--'}</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-[#f59e0b]" />
            <span className="text-slate-400">EMA50:</span>
            <span className="text-amber-300 font-semibold">{indicatorValues.ema50?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '--'}</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-[#a855f7]" />
            <span className="text-slate-400">EMA200:</span>
            <span className="text-purple-300 font-semibold">{indicatorValues.ema200?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '--'}</span>
          </div>
          {showSR && (
            <>
              <div className="h-3 w-px bg-dark-800" />
              <div className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-rose-500" />
                <span className="text-slate-400">Res:</span>
                <span className="text-rose-400 font-semibold">{indicatorValues.resistance?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '--'}</span>
              </div>
              <div className="flex items-center space-x-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-slate-400">Sup:</span>
                <span className="text-emerald-400 font-semibold">{indicatorValues.support?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '--'}</span>
              </div>
            </>
          )}
        </div>
      )}

      {/* Chart Canvas */}
      <div className="flex-1 relative w-full h-full min-h-[300px]">
        {loading && (
          <div className="absolute inset-0 bg-dark-950/60 backdrop-blur-[1px] flex items-center justify-center z-10">
            <div className="flex items-center space-x-2 text-xs font-mono text-slate-300">
              <div className="w-3.5 h-3.5 border-2 border-brand-gold border-t-transparent rounded-full animate-spin" />
              <span>Loading Binance OHLCV...</span>
            </div>
          </div>
        )}
        <div ref={chartContainerRef} className="w-full h-full" />
      </div>

      {/* Collapsible Trade Analysis & Retrospective Drawer */}
      {showTradeLog && (
        <div className="border-t border-dark-800 bg-dark-900/95 max-h-64 sm:max-h-72 overflow-y-auto flex flex-col z-20 shadow-2xl animate-in slide-in-from-bottom-4 duration-200">
          <div className="px-3.5 py-2 border-b border-dark-800 flex items-center justify-between bg-dark-950/80 sticky top-0 z-10">
            <div className="flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-brand-gold" />
              <span className="text-xs font-bold text-white tracking-wide">
                บันทึกการเข้าเทรด & เหตุผลได้/เสีย ({symbol})
              </span>
            </div>
            <span className="text-[11px] text-slate-400 font-mono">
              {tradeDetails.length} ออเดอร์ล่าสุด
            </span>
          </div>

          <div className="p-3 space-y-2">
            {tradeDetails.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-500 font-mono">
                ยังไม่มีประวัติการเข้าเทรดในคู่เหรียญนี้ ระบบจะบันทึกและมาร์คจุดทันทีเมื่อมีออเดอร์
              </div>
            ) : (
              tradeDetails.map((trade) => (
                <div
                  key={trade.id}
                  onClick={() => setSelectedTrade(selectedTrade?.id === trade.id ? null : trade)}
                  className={`p-3 rounded-xl border transition-all cursor-pointer ${
                    selectedTrade?.id === trade.id
                      ? 'bg-dark-800/90 border-brand-gold/50 shadow-md'
                      : 'bg-dark-950/60 border-dark-800 hover:border-dark-700 hover:bg-dark-900/80'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono uppercase ${
                          trade.direction === 'BUY'
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                            : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                        }`}
                      >
                        {trade.direction} #{trade.ticket}
                      </span>
                      <span className="text-xs font-bold text-white">{trade.strategy}</span>
                    </div>

                    <div className="flex items-center space-x-2 font-mono text-xs font-bold">
                      {trade.status === 'OPEN' ? (
                        <span className="px-2 py-0.5 rounded text-[10px] bg-blue-500/15 text-blue-400 border border-blue-500/30">
                          กำลังถือออเดอร์
                        </span>
                      ) : (
                        <span className={trade.profit >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                          {trade.profit >= 0 ? `+${trade.outcome_r}R (+$${trade.profit.toFixed(2)})` : `${trade.outcome_r}R (-$${Math.abs(trade.profit).toFixed(2)})`}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Trade Prices Strip */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono text-slate-400 mb-2 bg-dark-900/60 p-2 rounded-lg border border-dark-800/60">
                    <div>
                      <span className="text-slate-500 mr-1">Entry:</span>
                      <span className="text-slate-200 font-semibold">${trade.entry_price.toLocaleString()}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 mr-1">Exit:</span>
                      <span className="text-slate-200 font-semibold">
                        {trade.exit_price > 0 ? `$${trade.exit_price.toLocaleString()}` : '--'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 mr-1">SL:</span>
                      <span className="text-rose-400 font-semibold">${trade.sl.toLocaleString()}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 mr-1">TP:</span>
                      <span className="text-emerald-400 font-semibold">${trade.tp.toLocaleString()}</span>
                    </div>
                  </div>

                  {/* Why entered & Why won/lost explanations */}
                  <div className="space-y-1.5 text-xs">
                    <div className="flex items-start space-x-1.5 text-slate-300">
                      <span className="text-brand-gold font-semibold shrink-0">🎯 เข้าเพราะ:</span>
                      <span className="text-slate-300 leading-relaxed">{trade.why_entered}</span>
                    </div>
                    <div className="flex items-start space-x-1.5">
                      <span className="font-semibold shrink-0 text-slate-400">📊 ผลลัพธ์:</span>
                      <span
                        className={`leading-relaxed ${
                          trade.status === 'WIN'
                            ? 'text-emerald-300'
                            : trade.status === 'LOSS'
                            ? 'text-rose-300'
                            : 'text-blue-300'
                        }`}
                      >
                        {trade.why_won_lost}
                      </span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

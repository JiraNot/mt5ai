import React, { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickData, Time } from 'lightweight-charts';
import { fetchCandles, CandleItem, PositionItem } from '../services/api';

interface TradingChartProps {
  symbol: string;
  positions: PositionItem[];
  lastTick: { bid: number; ask: number; last: number; timestamp: number } | null;
}

const TIMEFRAMES = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1h', value: '1h' },
  { label: '4h', value: '4h' },
  { label: '1d', value: '1d' },
];

export const TradingChart: React.FC<TradingChartProps> = ({ symbol, positions, lastTick }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const priceLinesRef = useRef<any[]>([]);

  const [timeframe, setTimeframe] = useState('5m');
  const [loading, setLoading] = useState(true);
  const [candles, setCandles] = useState<CandleItem[]>([]);

  // 1. Initialize Lightweight Chart
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
      handleScale: { axisPressedMouseMove: true },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
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
      priceScaleId: '', // Overlay over chart bottom
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    // Handle Window Resize
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

  // 2. Fetch Candles when Symbol or Timeframe changes
  useEffect(() => {
    let isCancelled = false;
    setLoading(true);

    const loadData = async () => {
      try {
        const res = await fetchCandles(symbol, timeframe, 250);
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
  }, [symbol, timeframe]);

  // 3. Real-time Tick Updates to Current Candle
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

  // 4. Position Lines Overlay (Entry, SL, TP)
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    // Remove existing price lines
    priceLinesRef.current.forEach((line) => {
      try {
        candleSeriesRef.current?.removePriceLine(line);
      } catch (e) {}
    });
    priceLinesRef.current = [];

    // Filter positions for active symbol
    const activePositions = positions.filter((p) => p.symbol === symbol);

    activePositions.forEach((pos) => {
      // Entry Line
      const entryLine = candleSeriesRef.current?.createPriceLine({
        price: pos.open_price,
        color: '#1e88e5',
        lineWidth: 2,
        lineStyle: 0, // Solid
        axisLabelVisible: true,
        title: `ENTRY #${pos.ticket}`,
      });
      if (entryLine) priceLinesRef.current.push(entryLine);

      // Stop Loss Line
      if (pos.sl > 0) {
        const slLine = candleSeriesRef.current?.createPriceLine({
          price: pos.sl,
          color: '#f6465d',
          lineWidth: 2,
          lineStyle: 2, // Dashed
          axisLabelVisible: true,
          title: `SL`,
        });
        if (slLine) priceLinesRef.current.push(slLine);
      }

      // Take Profit Line
      if (pos.tp > 0) {
        const tpLine = candleSeriesRef.current?.createPriceLine({
          price: pos.tp,
          color: '#0ecb81',
          lineWidth: 2,
          lineStyle: 2, // Dashed
          axisLabelVisible: true,
          title: `TP`,
        });
        if (tpLine) priceLinesRef.current.push(tpLine);
      }
    });
  }, [positions, symbol]);

  return (
    <div className="flex-1 flex flex-col bg-dark-950 relative overflow-hidden border-r border-dark-800">
      {/* Chart Top Bar: Symbol Info & Timeframe Selectors */}
      <div className="h-10 border-b border-dark-800 px-3 flex items-center justify-between bg-dark-900/60 select-none">
        <div className="flex items-center space-x-2">
          <span className="font-bold text-xs text-white tracking-wider">{symbol}</span>
          <span className="text-[11px] text-slate-400 font-mono">PERPETUAL</span>
        </div>

        {/* Timeframe Buttons */}
        <div className="flex items-center space-x-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.value}
              onClick={() => setTimeframe(tf.value)}
              className={`px-2.5 py-0.5 rounded text-xs font-mono font-medium transition-colors ${
                timeframe === tf.value
                  ? 'bg-dark-700 text-brand-gold font-bold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart Canvas Container */}
      <div className="flex-1 relative w-full h-full">
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
    </div>
  );
};

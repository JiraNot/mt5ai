import React, { useEffect, useState } from 'react';
import {
  X,
  Save,
  Shield,
  Key,
  Bot,
  Send,
  Sliders,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  RefreshCw,
  Zap,
  ExternalLink,
  Terminal as TerminalIcon,
  Sparkles,
} from 'lucide-react';
import {
  fetchSettings,
  saveSettings,
  RuntimeSettings,
  fetchAIAuthStatus,
  testAIProvider,
  testBinanceApi,
  AIAuthItem,
} from '../services/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, onSaved }) => {
  const [activeTab, setActiveTab] = useState<'trading' | 'binance' | 'ai' | 'telegram'>('trading');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingBinance, setTestingBinance] = useState(false);
  const [binanceTestResult, setBinanceTestResult] = useState<{
    ok: boolean;
    message: string;
    balance?: number;
    currency?: string;
  } | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // AI Auth states (MobileIDE pattern)
  const [authItems, setAuthItems] = useState<AIAuthItem[]>([]);
  const [checkingAuth, setCheckingAuth] = useState(false);
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; message: string; latency_ms: number; status: string }>>({});

  // Form state
  const [formData, setFormData] = useState<Partial<RuntimeSettings>>({
    trading_mode: 'paper',
    primary_symbol: 'BTCUSDT',
    active_symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
    paper_initial_balance: 100000,
    risk_per_trade_pct: 0.01,
    max_daily_loss_pct: 0.03,
    max_open_positions: 3,
    min_rr: 2.0,
    entry_min_score: 70,
    binance_mode: 'paper',
    binance_base_url: 'https://testnet.binancefuture.com',
    binance_api_key: '',
    binance_api_secret: '',
    ai_provider: 'codex',
    openai_api_key: '',
    openai_model: 'gpt-4o',
    gemini_api_key: '',
    openrouter_api_key: '',
    openrouter_model: 'deepseek/deepseek-chat',
    vision_provider: 'deterministic',
    vision_min_score: 65,
    volume_filter_enabled: true,
    rsi_filter_enabled: true,
    telegram_enabled: false,
    telegram_bot_token: '',
    telegram_chat_id: '',
  });

  const [showBinanceSecret, setShowBinanceSecret] = useState(false);
  const [showAIKey, setShowAIKey] = useState(false);
  const [showTelegramToken, setShowTelegramToken] = useState(false);

  const refreshAuth = async (force = false) => {
    setCheckingAuth(true);
    try {
      const res = await fetchAIAuthStatus(force);
      if (res && res.ok && Array.isArray(res.items)) {
        setAuthItems(res.items);
      }
    } catch (err: any) {
      console.warn('AI Auth inspection error:', err);
    } finally {
      setCheckingAuth(false);
    }
  };

  const handleTestProvider = async (providerId: string) => {
    setTestingProvider(providerId);
    try {
      const res = await testAIProvider(providerId);
      if (res && res.result) {
        setTestResults(prev => ({
          ...prev,
          [providerId]: res.result,
        }));
        if (res.result.ok) {
          refreshAuth(true);
        }
      }
    } catch (err: any) {
      setTestResults(prev => ({
        ...prev,
        [providerId]: {
          ok: false,
          provider: providerId,
          status: 'error',
          latency_ms: 0,
          message: err?.message || 'การเชื่อมต่อล้มเหลว',
        },
      }));
    } finally {
      setTestingProvider(null);
    }
  };

  const handleTestBinance = async () => {
    setTestingBinance(true);
    setBinanceTestResult(null);
    try {
      const result = await testBinanceApi({
        binance_mode: formData.binance_mode || 'paper',
        binance_base_url: formData.binance_base_url || '',
        binance_api_key: formData.binance_api_key || '',
        binance_api_secret: formData.binance_api_secret || '',
      });
      setBinanceTestResult(result);
    } catch (err: any) {
      setBinanceTestResult({
        ok: false,
        message: err?.message || 'ตรวจสอบ Binance API ไม่สำเร็จ',
      });
    } finally {
      setTestingBinance(false);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    fetchSettings()
      .then((res) => {
        if (res.ok && res.settings) {
          setFormData(res.settings);
        }
      })
      .catch((err) => {
        setToast({ type: 'error', message: 'โหลดการตั้งค่าไม่สำเร็จ: ' + err.message });
      })
      .finally(() => setLoading(false));

    refreshAuth(true);
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && activeTab === 'ai') {
      refreshAuth(true);
    }
  }, [activeTab]);

  if (!isOpen) return null;

  const handleSave = async () => {
    setSaving(true);
    setToast(null);
    try {
      const res = await saveSettings(formData);
      if (res.ok) {
        setToast({ type: 'success', message: 'บันทึกการตั้งค่าสำเร็จ! ข้อมูลถูกนำไปใช้ทันทีโดยไม่ต้องรีสตาร์ต' });
        setFormData(res.settings);
        if (onSaved) onSaved();
        setTimeout(() => setToast(null), 3000);
      } else {
        setToast({ type: 'error', message: res.message || 'บันทึกไม่สำเร็จ' });
      }
    } catch (err: any) {
      setToast({ type: 'error', message: 'เกิดข้อผิดพลาดในการบันทึก: ' + err.message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-dark-900 border border-dark-700/80 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="px-5 py-4 border-b border-dark-800 flex items-center justify-between bg-dark-950/60">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-lg bg-brand-gold/10 text-brand-gold">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-wide">ตั้งค่าระบบ (Dynamic Settings)</h2>
              <p className="text-xs text-slate-400">ปรับแต่งการทำงานและ API Key ได้ทันทีโดยไม่ต้องแก้ไขไฟล์ .env</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-dark-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Tabs */}
        <div className="flex border-b border-dark-800 bg-dark-950/40 px-3 overflow-x-auto select-none">
          <button
            onClick={() => setActiveTab('trading')}
            className={`flex items-center space-x-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
              activeTab === 'trading'
                ? 'border-brand-gold text-brand-gold bg-brand-gold/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Shield className="w-4 h-4" />
            <span>การเทรด & ความเสี่ยง</span>
          </button>
          <button
            onClick={() => setActiveTab('binance')}
            className={`flex items-center space-x-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
              activeTab === 'binance'
                ? 'border-brand-gold text-brand-gold bg-brand-gold/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Key className="w-4 h-4" />
            <span>Binance Futures API</span>
          </button>
          <button
            onClick={() => setActiveTab('ai')}
            className={`flex items-center space-x-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
              activeTab === 'ai'
                ? 'border-brand-gold text-brand-gold bg-brand-gold/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Bot className="w-4 h-4" />
            <span>AI Council & โมเดล</span>
          </button>
          <button
            onClick={() => setActiveTab('telegram')}
            className={`flex items-center space-x-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
              activeTab === 'telegram'
                ? 'border-brand-gold text-brand-gold bg-brand-gold/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Send className="w-4 h-4" />
            <span>แจ้งเตือน Telegram</span>
          </button>
        </div>

        {/* Toast Notification */}
        {toast && (
          <div
            className={`mx-5 mt-4 p-3 rounded-lg flex items-center space-x-2 text-xs font-medium animate-in slide-in-from-top-2 duration-200 ${
              toast.type === 'success'
                ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-300'
                : 'bg-rose-500/10 border border-rose-500/30 text-rose-300'
            }`}
          >
            {toast.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
            <span>{toast.message}</span>
          </div>
        )}

        {/* Tab Content Body */}
        <div className="p-5 flex-1 overflow-y-auto space-y-4">
          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center space-y-3 text-slate-400">
              <RefreshCw className="w-6 h-6 animate-spin text-brand-gold" />
              <span className="text-xs">กำลังโหลดการตั้งค่าจากระบบ...</span>
            </div>
          ) : (
            <>
              {/* TAB 1: TRADING & RISK */}
              {activeTab === 'trading' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                      โหมดการทำงาน (Trading Mode)
                    </label>
                    <div className="grid grid-cols-3 gap-2">
                      {(['paper', 'demo', 'live'] as const).map((m) => (
                        <button
                          key={m}
                          type="button"
                          onClick={() => setFormData({ ...formData, trading_mode: m })}
                          className={`py-2.5 px-3 rounded-xl border text-xs font-bold uppercase transition-all ${
                            formData.trading_mode === m
                              ? m === 'live'
                                ? 'bg-rose-500/20 border-rose-500 text-rose-300 shadow-md shadow-rose-500/10'
                                : 'bg-brand-gold/20 border-brand-gold text-brand-gold shadow-md shadow-brand-gold/10'
                              : 'bg-dark-950/60 border-dark-700 text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          {m}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">คู่เหรียญหลัก (Primary Symbol)</label>
                      <input
                        type="text"
                        value={formData.primary_symbol || ''}
                        onChange={(e) => setFormData({ ...formData, primary_symbol: e.target.value.toUpperCase() })}
                        className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                        placeholder="BTCUSDT"
                      />
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs font-semibold text-slate-300">เหรียญใน Watchlist (คั่นด้วยจุลภาค)</label>
                        <span className="text-[10px] text-slate-400">คลิกเพื่อเพิ่มเหรียญเล็ก</span>
                      </div>
                      <input
                        type="text"
                        value={Array.isArray(formData.active_symbols) ? formData.active_symbols.join(', ') : formData.active_symbols || ''}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            active_symbols: e.target.value.split(',').map((s) => s.trim().toUpperCase()),
                          })
                        }
                        className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                        placeholder="BTCUSDT, ETHUSDT, SOLUSDT"
                      />
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {['SOLUSDT', 'DOGEUSDT', 'XRPUSDT', 'SUIUSDT', 'ADAUSDT'].map((sym) => {
                          const currentList = Array.isArray(formData.active_symbols) ? formData.active_symbols : [];
                          const isIncluded = currentList.includes(sym);
                          return (
                            <button
                              key={sym}
                              type="button"
                              onClick={() => {
                                if (isIncluded) {
                                  setFormData({
                                    ...formData,
                                    active_symbols: currentList.filter((s) => s !== sym),
                                  });
                                } else {
                                  setFormData({
                                    ...formData,
                                    active_symbols: [...currentList, sym],
                                  });
                                }
                              }}
                              className={`px-1.5 py-0.5 text-[10px] font-mono rounded border transition-colors ${
                                isIncluded
                                  ? 'bg-brand-gold/20 border-brand-gold text-brand-gold font-bold'
                                  : 'bg-dark-950 border-dark-800 text-slate-400 hover:text-white'
                              }`}
                            >
                              {isIncluded ? `✓ ${sym}` : `+ ${sym}`}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs font-semibold text-slate-300">ความเสี่ยงต่อไม้ (Risk %)</label>
                        <div className="flex items-center space-x-1">
                          {[
                            { label: '1%', val: 0.01, daily: 0.03 },
                            { label: '3%', val: 0.03, daily: 0.10 },
                            { label: '5%', val: 0.05, daily: 0.15 },
                          ].map((p) => {
                            const isSelected = Math.abs((formData.risk_per_trade_pct || 0.01) - p.val) < 0.005;
                            return (
                              <button
                                key={p.label}
                                type="button"
                                onClick={() =>
                                  setFormData({
                                    ...formData,
                                    risk_per_trade_pct: p.val,
                                    max_daily_loss_pct: Math.max(formData.max_daily_loss_pct || 0.03, p.daily),
                                  })
                                }
                                className={`px-1.5 py-0.5 text-[10px] font-mono font-bold rounded transition-colors ${
                                  isSelected
                                    ? 'bg-brand-gold text-dark-950 font-extrabold'
                                    : 'bg-dark-800 text-slate-400 hover:text-white border border-dark-700'
                                }`}
                                title={`ตั้งค่าความเสี่ยง ${p.label}`}
                              >
                                {p.label}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                      <div className="relative">
                        <input
                          type="number"
                          step="0.1"
                          min="0.1"
                          max="10"
                          value={((formData.risk_per_trade_pct || 0.01) * 100).toFixed(1)}
                          onChange={(e) =>
                            setFormData({ ...formData, risk_per_trade_pct: parseFloat(e.target.value) / 100 })
                          }
                          className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold pr-8"
                        />
                        <span className="absolute right-3 top-2.5 text-xs text-slate-500 font-mono">%</span>
                      </div>
                      <span className="text-[10px] text-slate-500 mt-0.5 block">
                        {(formData.risk_per_trade_pct || 0.01) >= 0.03 ? '🔥 โหมดเติบโตเร็ว (เสี่ยง 3% - 5%)' : '🛡️ โหมดอนุรักษ์นิยม (1% - 2%)'}
                      </span>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">ขาดทุนสูงสุดต่อวัน (Daily Limit)</label>
                      <div className="relative">
                        <input
                          type="number"
                          step="0.5"
                          min="1"
                          max="20"
                          value={((formData.max_daily_loss_pct || 0.03) * 100).toFixed(1)}
                          onChange={(e) =>
                            setFormData({ ...formData, max_daily_loss_pct: parseFloat(e.target.value) / 100 })
                          }
                          className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold pr-8"
                        />
                        <span className="absolute right-3 top-2.5 text-xs text-slate-500 font-mono">%</span>
                      </div>
                      <span className="text-[10px] text-slate-500 mt-0.5 block">หยุดเทรดหากแตะลิมิต</span>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">R:R ขั้นต่ำ (Min R:R)</label>
                      <input
                        type="number"
                        step="0.1"
                        min="1.0"
                        max="10.0"
                        value={formData.min_rr || 2.0}
                        onChange={(e) => setFormData({ ...formData, min_rr: parseFloat(e.target.value) })}
                        className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                      />
                      <span className="text-[10px] text-slate-500 mt-0.5 block">ขั้นต่ำ 1:2.0 ตามกฎ</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">จำนวนออเดอร์พร้อมกันสูงสุด</label>
                      <input
                        type="number"
                        min="1"
                        max="10"
                        value={formData.max_open_positions || 3}
                        onChange={(e) => setFormData({ ...formData, max_open_positions: parseInt(e.target.value) })}
                        className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                      />
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs font-semibold text-slate-300">เงินทุนจำลอง Paper (USDT)</label>
                        <div className="flex items-center space-x-1">
                          {[
                            { label: '$10', val: 10 },
                            { label: '$100', val: 100 },
                            { label: '$1k', val: 1000 },
                          ].map((b) => (
                            <button
                              key={b.label}
                              type="button"
                              onClick={() => setFormData({ ...formData, paper_initial_balance: b.val })}
                              className={`px-1.5 py-0.5 text-[10px] font-mono font-bold rounded transition-colors ${
                                formData.paper_initial_balance === b.val
                                  ? 'bg-brand-gold text-dark-950 font-extrabold'
                                  : 'bg-dark-800 text-slate-400 hover:text-white border border-dark-700'
                              }`}
                            >
                              {b.label}
                            </button>
                          ))}
                        </div>
                      </div>
                      <input
                        type="number"
                        step="1"
                        min="1"
                        value={formData.paper_initial_balance ?? 100}
                        onChange={(e) => setFormData({ ...formData, paper_initial_balance: parseFloat(e.target.value) || 0 })}
                        className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                      />
                      <span className="text-[10px] text-slate-500 mt-0.5 block">
                        {(formData.paper_initial_balance || 100) <= 50 ? '🧪 โหมดจำลองพอร์ตเล็ก Micro ($10 - $50)' : 'ทุนจำลองสำหรับทดสอบระบบ'}
                      </span>
                    </div>
                  </div>

                  {/* Smart Filters */}
                  <div className="p-3 bg-dark-950/60 border border-dark-800 rounded-xl space-y-3">
                    <div className="text-xs font-bold text-slate-200">ตัวกรองโมเมนตัมและวอลุ่ม (Institutional Confirmation)</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <label className="flex items-center justify-between p-2.5 bg-dark-900 border border-dark-700/60 rounded-xl cursor-pointer hover:border-dark-600 transition-colors">
                        <div>
                          <div className="text-xs font-semibold text-white">Volume Spike Filter</div>
                          <div className="text-[10px] text-slate-400">กรองวอลุ่มสถาบัน ยืนยันการเบรกหลอก</div>
                        </div>
                        <input
                          type="checkbox"
                          checked={formData.volume_filter_enabled ?? true}
                          onChange={(e) => setFormData({ ...formData, volume_filter_enabled: e.target.checked })}
                          className="w-4 h-4 rounded text-brand-gold bg-dark-950 border-dark-700 focus:ring-0 cursor-pointer"
                        />
                      </label>

                      <label className="flex items-center justify-between p-2.5 bg-dark-900 border border-dark-700/60 rounded-xl cursor-pointer hover:border-dark-600 transition-colors">
                        <div>
                          <div className="text-xs font-semibold text-white">RSI Momentum Filter</div>
                          <div className="text-[10px] text-slate-400">ป้องกันซื้อติดดอย Overbought / ขาย Oversold</div>
                        </div>
                        <input
                          type="checkbox"
                          checked={formData.rsi_filter_enabled ?? true}
                          onChange={(e) => setFormData({ ...formData, rsi_filter_enabled: e.target.checked })}
                          className="w-4 h-4 rounded text-brand-gold bg-dark-950 border-dark-700 focus:ring-0 cursor-pointer"
                        />
                      </label>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: BINANCE API */}
              {activeTab === 'binance' && (
                <div className="space-y-4">
                  <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-xs text-amber-200/90 leading-relaxed">
                    💡 <strong>ปลอดภัย:</strong> คีย์และ Secret จะถูกเข้ารหัส Fernet ก่อนจัดเก็บ
                    ไม่ถูกส่งกลับไปยังหน้าจอ และนำไปใช้งานทันทีโดยไม่ต้องแก้ไขไฟล์ <code className="bg-dark-900 px-1 py-0.5 rounded">.env</code>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">สภาพแวดล้อม Binance</label>
                    <div className="grid grid-cols-3 gap-2">
                      {(['paper', 'testnet', 'live'] as const).map((bm) => (
                        <button
                          key={bm}
                          type="button"
                          onClick={() => {
                            const url =
                              bm === 'live'
                                ? 'https://fapi.binance.com'
                                : 'https://testnet.binancefuture.com';
                            setFormData({ ...formData, binance_mode: bm, binance_base_url: url });
                            setBinanceTestResult(null);
                          }}
                          className={`py-2 px-3 rounded-xl border text-xs font-bold uppercase transition-all ${
                            formData.binance_mode === bm
                              ? 'bg-brand-gold/20 border-brand-gold text-brand-gold'
                              : 'bg-dark-950/60 border-dark-700 text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          {bm}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Binance Futures Base URL</label>
                    <input
                      type="text"
                      value={formData.binance_base_url || ''}
                      onChange={(e) => {
                        setFormData({ ...formData, binance_base_url: e.target.value });
                        setBinanceTestResult(null);
                      }}
                      className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Binance API Key</label>
                    <input
                      type="text"
                      value={formData.binance_api_key || ''}
                      onChange={(e) => {
                        setFormData({ ...formData, binance_api_key: e.target.value });
                        setBinanceTestResult(null);
                      }}
                      className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                      placeholder="ใส่ API Key จาก Binance (ถ้าเว้นไว้คงค่าเดิม)"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Binance API Secret</label>
                    <div className="relative">
                      <input
                        type={showBinanceSecret ? 'text' : 'password'}
                        value={formData.binance_api_secret || ''}
                        onChange={(e) => {
                          setFormData({ ...formData, binance_api_secret: e.target.value });
                          setBinanceTestResult(null);
                        }}
                        className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold pr-10"
                        placeholder="ใส่ API Secret จาก Binance (ถ้าเว้นไว้คงค่าเดิม)"
                      />
                      <button
                        type="button"
                        onClick={() => setShowBinanceSecret(!showBinanceSecret)}
                        className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-200"
                      >
                        {showBinanceSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  <div className="space-y-2 pt-1">
                    <button
                      type="button"
                      onClick={handleTestBinance}
                      disabled={testingBinance || formData.binance_mode !== 'testnet'}
                      className="px-4 py-2 rounded-xl border border-brand-gold/50 bg-brand-gold/10 hover:bg-brand-gold/20 text-xs font-bold text-brand-gold flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {testingBinance ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                      <span>{testingBinance ? 'กำลังตรวจสอบ...' : 'ทดสอบ Binance API'}</span>
                    </button>
                    <p className="text-[10px] text-slate-500">
                      ทดสอบอ่านข้อมูลบัญชี Binance Futures Testnet เท่านั้น ไม่มีการส่งคำสั่งซื้อขาย
                    </p>
                    {binanceTestResult && (
                      <div className={`flex items-start space-x-2 rounded-lg border px-3 py-2 text-xs ${
                        binanceTestResult.ok
                          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                          : 'border-rose-500/30 bg-rose-500/10 text-rose-300'
                      }`}>
                        {binanceTestResult.ok
                          ? <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
                          : <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />}
                        <span>
                          {binanceTestResult.message}
                          {binanceTestResult.ok && typeof binanceTestResult.balance === 'number'
                            ? ` • Balance: ${binanceTestResult.balance.toFixed(2)} ${binanceTestResult.currency || 'USDT'}`
                            : ''}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 3: AI COUNCIL */}
              {activeTab === 'ai' && (
                <div className="space-y-4">
                  {/* Account Login & Auth Inspection Card (MobileIDE Pattern) */}
                  <div className="p-3.5 bg-dark-950/80 border border-purple-500/20 rounded-xl space-y-3">
                    <div className="flex items-center justify-between border-b border-dark-800 pb-2.5">
                      <div className="flex items-center space-x-2">
                        <Sparkles className="w-4 h-4 text-purple-400" />
                        <div>
                          <div className="text-xs font-bold text-white tracking-wide">
                            สถานะการล็อกอิน AI (Account Login & CLI Sessions)
                          </div>
                          <div className="text-[10px] text-slate-400">
                            ตรวจสอบสถานะเซสชันและ CLI อัตโนมัติในเครื่อง ไม่กิน Quota หรือตัดเหรียญ
                          </div>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => refreshAuth(true)}
                        disabled={checkingAuth}
                        className="flex items-center space-x-1 px-2.5 py-1 text-[11px] font-semibold text-slate-300 hover:text-white bg-dark-900 border border-dark-700 hover:border-dark-600 rounded-lg transition-colors"
                        title="ตรวจสถานะการล็อกอินใหม่"
                      >
                        <RefreshCw className={`w-3 h-3 ${checkingAuth ? 'animate-spin text-purple-400' : ''}`} />
                        <span>{checkingAuth ? 'กำลังตรวจ…' : 'ตรวจสถานะใหม่'}</span>
                      </button>
                    </div>

                    {/* Providers Status List */}
                    <div className="space-y-2.5">
                      {(authItems.length > 0
                        ? authItems
                        : [
                            { id: 'codex', name: 'ChatGPT / Codex', auth_type: 'oauth-login', state: 'unknown', note: 'ตรวจสอบสถานะ Codex CLI…' },
                            { id: 'gemini', name: 'Google Gemini / Antigravity', auth_type: 'oauth-login', state: 'unknown', note: 'ตรวจสอบสถานะ Google OAuth…' },
                            { id: 'openai', name: 'OpenAI Direct API', auth_type: 'api-key', state: 'unknown', note: 'ตรวจสอบ API Key…' },
                            { id: 'openrouter', name: 'OpenRouter', auth_type: 'api-key', state: 'unknown', note: 'ตรวจสอบ API Key…' },
                          ]
                      ).map((item) => {
                        const test = testResults[item.id];
                        const isTesting = testingProvider === item.id;
                        const isPrimary = formData.ai_provider === item.id;

                        let badgeColor = 'bg-slate-800/80 text-slate-400 border-slate-700';
                        let badgeLabel = 'ไม่ทราบสถานะ';
                        let dotColor = 'bg-slate-400';

                        const isAuth = item.state === 'authenticated' || Boolean(test && test.ok);
                        if (isAuth) {
                          badgeColor = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40';
                          badgeLabel = 'เข้าสู่ระบบแล้ว (Authenticated)';
                          dotColor = 'bg-emerald-400 animate-pulse';
                        } else if (item.state === 'configured') {
                          badgeColor = 'bg-sky-500/15 text-sky-300 border-sky-500/40';
                          badgeLabel = 'ตั้งค่าแล้ว (Configured)';
                          dotColor = 'bg-sky-400';
                        } else if (item.state === 'login_required') {
                          badgeColor = 'bg-amber-500/15 text-amber-300 border-amber-500/40';
                          badgeLabel = 'ต้องล็อกอิน (Login Required)';
                          dotColor = 'bg-amber-400';
                        }

                        return (
                          <div
                            key={item.id}
                            className={`p-2.5 rounded-xl border transition-all ${
                              isPrimary
                                ? 'bg-purple-950/20 border-purple-500/40 ring-1 ring-purple-500/20'
                                : 'bg-dark-900/70 border-dark-800 hover:border-dark-700'
                            }`}
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="flex items-center space-x-2">
                                <span className="text-xs font-bold text-white">{item.name}</span>
                                {item.account_label && (
                                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-dark-800 text-slate-300 border border-dark-700">
                                    {item.account_label}
                                  </span>
                                )}
                                {isPrimary && (
                                  <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                                    ★ AI หลัก
                                  </span>
                                )}
                              </div>

                              <div className="flex items-center space-x-1.5">
                                <span className={`inline-flex items-center space-x-1 px-2 py-0.5 text-[10px] font-semibold rounded-full border ${badgeColor}`}>
                                  <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
                                  <span>{badgeLabel}</span>
                                </span>

                                <button
                                  type="button"
                                  onClick={() => handleTestProvider(item.id)}
                                  disabled={isTesting}
                                  className="flex items-center space-x-1 px-2 py-1 text-[10px] font-bold text-amber-300 hover:text-white bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 rounded-lg transition-colors"
                                  title="ทดสอบการเชื่อมต่อและความหน่วง (Latency)"
                                >
                                  <Zap className={`w-3 h-3 ${isTesting ? 'animate-bounce text-amber-400' : ''}`} />
                                  <span>{isTesting ? 'กำลังเทส…' : '⚡ ทดสอบ'}</span>
                                </button>

                                {(item.id === 'codex' || item.id === 'gemini') && (
                                  <a
                                    href="/terminal"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center space-x-1 px-2 py-1 text-[10px] font-bold text-sky-300 hover:text-white bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/30 rounded-lg transition-colors"
                                    title="เปิด Web Terminal เพื่อล็อกอิน OAuth ผ่านเบราว์เซอร์"
                                  >
                                    <TerminalIcon className="w-3 h-3" />
                                    <span>Terminal</span>
                                    <ExternalLink className="w-2.5 h-2.5 opacity-70" />
                                  </a>
                                )}

                                {!isPrimary && (
                                  <button
                                    type="button"
                                    onClick={() => setFormData({ ...formData, ai_provider: item.id as any })}
                                    className="px-2 py-1 text-[10px] font-medium text-slate-400 hover:text-white bg-dark-950 border border-dark-700 rounded-lg transition-colors"
                                  >
                                    เลือกใช้
                                  </button>
                                )}
                              </div>
                            </div>

                            <div className="mt-1 text-[11px] text-slate-400 leading-tight">
                              {item.note}
                            </div>

                            {/* Live Test Feedback */}
                            {test && (
                              <div
                                className={`mt-2 p-2 px-2.5 rounded-lg text-[11px] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 border ${
                                  test.ok
                                    ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                                    : test.status === 'exhausted'
                                    ? 'bg-amber-500/15 text-amber-200 border-amber-500/30'
                                    : 'bg-rose-500/10 text-rose-300 border-rose-500/20'
                                }`}
                              >
                                <div className="flex items-center space-x-1.5">
                                  {test.status === 'exhausted' && <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                                  <span>{test.message}</span>
                                </div>
                                {test.latency_ms > 0 && (
                                  <span className="text-[10px] font-mono opacity-75 shrink-0">{test.latency_ms}ms</span>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Active AI Provider Switcher */}
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">ผู้ให้บริการ AI หลักสำหรับวิเคราะห์การเทรด</label>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      {[
                        { id: 'codex', label: 'Codex / ChatGPT' },
                        { id: 'openai', label: 'OpenAI Direct' },
                        { id: 'gemini', label: 'Google Gemini' },
                        { id: 'openrouter', label: 'OpenRouter' },
                      ].map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => setFormData({ ...formData, ai_provider: item.id as any })}
                          className={`py-2 px-3 rounded-xl border text-xs font-bold transition-all ${
                            formData.ai_provider === item.id
                              ? 'bg-purple-500/20 border-purple-500 text-purple-300 shadow-md shadow-purple-500/10'
                              : 'bg-dark-950/60 border-dark-700 text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Provider Specific Input Forms */}
                  {formData.ai_provider === 'openai' && (
                    <div className="space-y-3 p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1">OpenAI API Key</label>
                        <div className="relative">
                          <input
                            type={showAIKey ? 'text' : 'password'}
                            value={formData.openai_api_key || ''}
                            onChange={(e) => setFormData({ ...formData, openai_api_key: e.target.value })}
                            className="w-full bg-dark-900 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold pr-10"
                            placeholder="sk-proj-..."
                          />
                          <button
                            type="button"
                            onClick={() => setShowAIKey(!showAIKey)}
                            className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-200"
                          >
                            {showAIKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1">โมเดล OpenAI</label>
                        <input
                          type="text"
                          value={formData.openai_model || 'gpt-4o'}
                          onChange={(e) => setFormData({ ...formData, openai_model: e.target.value })}
                          className="w-full bg-dark-900 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                        />
                      </div>
                    </div>
                  )}

                  {formData.ai_provider === 'gemini' && (
                    <div className="space-y-3 p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1">Gemini API Key (ตัวเลือกเสริม หากไม่ใช้ Antigravity OAuth)</label>
                        <input
                          type="password"
                          value={formData.gemini_api_key || ''}
                          onChange={(e) => setFormData({ ...formData, gemini_api_key: e.target.value })}
                          className="w-full bg-dark-900 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                          placeholder="AIzaSy... (เว้นว่างไว้หากล็อกอินผ่าน Terminal แล้ว)"
                        />
                      </div>
                    </div>
                  )}

                  {formData.ai_provider === 'openrouter' && (
                    <div className="space-y-3 p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1">OpenRouter API Key</label>
                        <input
                          type="password"
                          value={formData.openrouter_api_key || ''}
                          onChange={(e) => setFormData({ ...formData, openrouter_api_key: e.target.value })}
                          className="w-full bg-dark-900 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                          placeholder="sk-or-v1-..."
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1">โมเดล OpenRouter</label>
                        <input
                          type="text"
                          value={formData.openrouter_model || 'deepseek/deepseek-chat'}
                          onChange={(e) => setFormData({ ...formData, openrouter_model: e.target.value })}
                          className="w-full bg-dark-900 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                        />
                      </div>
                    </div>
                  )}

                  {formData.ai_provider === 'codex' && (
                    <div className="p-3 bg-dark-950/60 border border-dark-800 rounded-xl space-y-2">
                      <div className="text-xs text-slate-300 flex items-center justify-between">
                        <span>ใช้งาน Codex CLI / ChatGPT OAuth Session อัตโนมัติ</span>
                        <a
                          href="/terminal"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[11px] font-semibold text-purple-400 hover:text-purple-300 flex items-center space-x-1"
                        >
                          <span>เปิด Terminal เพื่อล็อกอิน</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    </div>
                  )}

                  {/* AI Vision & Chart Analysis */}
                  <div className="p-3 bg-dark-950/60 border border-dark-800 rounded-xl space-y-3">
                    <div className="text-xs font-bold text-slate-200">ระบบวิเคราะห์ภาพกราฟแท่งเทียน (Multimodal AI Vision)</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-semibold text-slate-300 mb-1">เอนจิ้นวิเคราะห์รูปกราฟ</label>
                        <select
                          value={formData.vision_provider || 'deterministic'}
                          onChange={(e) => setFormData({ ...formData, vision_provider: e.target.value as any })}
                          className="w-full bg-dark-900 border border-dark-700 rounded-xl px-3 py-2 text-xs font-medium text-white focus:outline-none focus:border-brand-gold"
                        >
                          <option value="deterministic">⚡ Deterministic Engine (เร็วสุด 0ms, แม่นยำ)</option>
                          <option value="gpt-4o">🤖 OpenAI GPT-4o Vision</option>
                          <option value="claude-3-5">🧠 Claude 3.5 Sonnet Vision</option>
                          <option value="deepseek-vision">👁 DeepSeek Vision (OpenRouter)</option>
                        </select>
                      </div>

                      <div>
                        <div className="flex justify-between items-center mb-1">
                          <label className="text-[11px] font-semibold text-slate-300">คะแนนขั้นต่ำเพื่อส่งให้ Risk Engine</label>
                          <span className="text-xs font-mono font-bold text-brand-gold">{formData.entry_min_score ?? 70}%</span>
                        </div>
                        <input
                          type="range"
                          min="50"
                          max="90"
                          step="5"
                          value={formData.entry_min_score ?? 70}
                          onChange={(e) => setFormData({ ...formData, entry_min_score: parseInt(e.target.value) })}
                          className="w-full accent-brand-gold bg-dark-900 rounded-lg cursor-pointer"
                        />
                        <div className="text-[10px] text-slate-500 mt-0.5">คะแนนนี้กำหนดเกณฑ์ triage, AI Council และ AI confidence; ทุกคำสั่งยังต้องผ่าน Risk Engine, SL และ TP</div>
                      </div>

                      <div>
                        <div className="flex justify-between items-center mb-1">
                          <label className="text-[11px] font-semibold text-slate-300">เกณฑ์คะแนนยืนยันภาพขั้นต่ำ (Vision Score)</label>
                          <span className="text-xs font-mono font-bold text-brand-gold">{formData.vision_min_score || 65}%</span>
                        </div>
                        <input
                          type="range"
                          min="50"
                          max="90"
                          step="5"
                          value={formData.vision_min_score || 65}
                          onChange={(e) => setFormData({ ...formData, vision_min_score: parseInt(e.target.value) })}
                          className="w-full accent-brand-gold bg-dark-900 rounded-lg cursor-pointer"
                        />
                        <div className="flex justify-between text-[10px] text-slate-500 mt-0.5">
                          <span>50% (ผ่อนปรน)</span>
                          <span>70% (สมดุล)</span>
                          <span>90% (เข้มงวด)</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 4: TELEGRAM */}
              {activeTab === 'telegram' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-dark-950/60 border border-dark-800 rounded-xl">
                    <div>
                      <div className="text-xs font-bold text-white">เปิดการแจ้งเตือน Telegram</div>
                      <div className="text-[11px] text-slate-400">ส่งแจ้งเตือนการเปิด/ปิดออเดอร์, ขยับ BE, และสรุปผลรายวัน</div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.telegram_enabled || false}
                        onChange={(e) => setFormData({ ...formData, telegram_enabled: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-dark-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand-gold"></div>
                    </label>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Telegram Bot Token</label>
                    <div className="relative">
                      <input
                        type={showTelegramToken ? 'text' : 'password'}
                        value={formData.telegram_bot_token || ''}
                        onChange={(e) => setFormData({ ...formData, telegram_bot_token: e.target.value })}
                        className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold pr-10"
                        placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
                      />
                      <button
                        type="button"
                        onClick={() => setShowTelegramToken(!showTelegramToken)}
                        className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-200"
                      >
                        {showTelegramToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Telegram Chat ID</label>
                    <input
                      type="text"
                      value={formData.telegram_chat_id || ''}
                      onChange={(e) => setFormData({ ...formData, telegram_chat_id: e.target.value })}
                      className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                      placeholder="-100123456789 หรือ 987654321"
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3.5 border-t border-dark-800 bg-dark-950/80 flex items-center justify-between">
          <div className="text-[11px] text-slate-400">
            {formData.updated_at ? `อัปเดตล่าสุด: ${new Date(formData.updated_at).toLocaleTimeString()}` : ''}
          </div>
          <div className="flex items-center space-x-2.5">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl border border-dark-700 hover:bg-dark-800 text-xs font-semibold text-slate-300 transition-colors"
            >
              ยกเลิก
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="px-5 py-2 rounded-xl bg-brand-gold hover:bg-amber-400 text-dark-950 text-xs font-bold flex items-center space-x-1.5 shadow-lg shadow-brand-gold/10 active:scale-95 transition-all disabled:opacity-50"
            >
              {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              <span>{saving ? 'กำลังบันทึก...' : 'บันทึกการตั้งค่า'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

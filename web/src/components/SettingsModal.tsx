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
} from 'lucide-react';
import { fetchSettings, saveSettings, RuntimeSettings } from '../services/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, onSaved }) => {
  const [activeTab, setActiveTab] = useState<'trading' | 'binance' | 'ai' | 'telegram'>('trading');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

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
    telegram_enabled: false,
    telegram_bot_token: '',
    telegram_chat_id: '',
  });

  const [showBinanceSecret, setShowBinanceSecret] = useState(false);
  const [showAIKey, setShowAIKey] = useState(false);
  const [showTelegramToken, setShowTelegramToken] = useState(false);

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
  }, [isOpen]);

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
                      <label className="block text-xs font-semibold text-slate-300 mb-1">เหรียญใน Watchlist (คั่นด้วยจุลภาค)</label>
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
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-300 mb-1">ความเสี่ยงต่อไม้ (Risk %)</label>
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
                      <span className="text-[10px] text-slate-500 mt-0.5 block">แนะนำ 1.0% - 2.0%</span>
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
                      <label className="block text-xs font-semibold text-slate-300 mb-1">เงินทุนจำลอง Paper (USDT)</label>
                      <input
                        type="number"
                        step="1000"
                        min="100"
                        value={formData.paper_initial_balance || 100000}
                        onChange={(e) => setFormData({ ...formData, paper_initial_balance: parseFloat(e.target.value) })}
                        className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                      />
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
                      onChange={(e) => setFormData({ ...formData, binance_base_url: e.target.value })}
                      className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Binance API Key</label>
                    <input
                      type="text"
                      value={formData.binance_api_key || ''}
                      onChange={(e) => setFormData({ ...formData, binance_api_key: e.target.value })}
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
                        onChange={(e) => setFormData({ ...formData, binance_api_secret: e.target.value })}
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
                </div>
              )}

              {/* TAB 3: AI COUNCIL */}
              {activeTab === 'ai' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">ผู้ให้บริการ AI หลัก</label>
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
                        <label className="block text-xs font-semibold text-slate-300 mb-1">Gemini API Key</label>
                        <input
                          type="password"
                          value={formData.gemini_api_key || ''}
                          onChange={(e) => setFormData({ ...formData, gemini_api_key: e.target.value })}
                          className="w-full bg-dark-900 border border-dark-700 rounded-xl px-3.5 py-2 text-xs font-mono text-white focus:outline-none focus:border-brand-gold"
                          placeholder="AIzaSy..."
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
                      <div className="text-xs text-slate-300">
                        ใช้งาน Codex CLI / ChatGPT OAuth Session อัตโนมัติ (สามารถกดปุ่ม <strong>AI LOGIN</strong> บนเมนูบาร์เพื่อ Login ผ่านเบราว์เซอร์ได้)
                      </div>
                    </div>
                  )}
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

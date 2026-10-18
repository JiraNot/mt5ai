import React, { useState } from 'react';
import {
  BookOpen,
  X,
  ShieldCheck,
  Key,
  AlertTriangle,
  Coins,
  CheckCircle2,
  ExternalLink,
  Lock,
  ArrowRight,
  TrendingUp,
  HelpCircle,
  Cpu,
  Layers,
  Sparkles,
  Zap,
} from 'lucide-react';

interface UserGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenSettings?: () => void;
}

export const UserGuideModal: React.FC<UserGuideModalProps> = ({
  isOpen,
  onClose,
  onOpenSettings,
}) => {
  const [activeTab, setActiveTab] = useState<'status' | 'journey' | 'api' | 'strategy' | 'safety'>('status');

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-dark-900 border border-dark-700/80 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-dark-800 flex items-center justify-between bg-dark-950/70 shrink-0">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-base font-bold text-white tracking-wide">คู่มือการใช้งาน & เส้นทางสู่เงินจริง</h2>
                <span className="text-[10px] bg-brand-gold/15 text-brand-gold border border-brand-gold/30 px-2 py-0.5 rounded-full font-mono font-semibold">
                  OFFICIAL GUIDE
                </span>
              </div>
              <p className="text-xs text-slate-400">วิธีซ้อมพอร์ต $10, การสร้าง Binance API, และข้อควรระวังก่อนลงเงินจริง</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-dark-800 transition-colors"
            title="ปิดคู่มือ"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center border-b border-dark-800 bg-dark-950/40 px-2 sm:px-4 overflow-x-auto no-scrollbar shrink-0">
          {[
            { id: 'status', label: 'สถานะระบบปัจจุบัน', icon: Cpu },
            { id: 'journey', label: '4 สเต็ปสู่เงินจริง', icon: ArrowRight },
            { id: 'api', label: 'วิธีต่อ Binance API', icon: Key },
            { id: 'strategy', label: 'กลยุทธ์พอร์ต $10', icon: Coins },
            { id: 'safety', label: 'ระบบความปลอดภัย', icon: ShieldCheck },
          ].map((t) => {
            const Icon = t.icon;
            const isActive = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id as any)}
                className={`flex items-center space-x-2 px-3.5 py-3 text-xs font-semibold border-b-2 transition-all whitespace-nowrap ${
                  isActive
                    ? 'border-cyan-400 text-cyan-300 bg-cyan-500/5'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{t.label}</span>
              </button>
            );
          })}
        </div>

        {/* Content Body */}
        <div className="p-5 flex-1 overflow-y-auto space-y-4 text-slate-200 text-xs sm:text-sm">
          {/* TAB 1: SYSTEM STATUS */}
          {activeTab === 'status' && (
            <div className="space-y-4">
              <div className="p-4 bg-dark-950/70 border border-dark-800 rounded-xl space-y-3">
                <div className="flex items-center space-x-2">
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="font-bold text-white text-sm sm:text-base">ตอนนี้ระบบรองรับอะไรบ้างแล้ว?</span>
                </div>
                <p className="text-slate-300 text-xs leading-relaxed">
                  ระบบ ApexTrader AI Terminal ถูกออกแบบตามมาตรฐานสถาปัตยกรรมระดับสถาบัน เพื่อความปลอดภัยของเงินทุน โดยแบ่งโหมดการทำงานออกเป็น 3 ระดับอย่างเข้มงวด:
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
                  <div className="p-3 bg-dark-900 border border-blue-500/30 rounded-xl space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-blue-400 text-xs font-mono uppercase">1. โหมด PAPER</span>
                      <span className="text-[10px] bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded font-bold">พร้อม 100%</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      ดึงข้อมูลราคาสดแบบ Real-time จาก Binance และจำลองการออกคำสั่งเสมือนจริงในเครื่อง เพื่อทดสอบโมเดล AI และดูกำไร/ขาดทุน
                    </p>
                  </div>

                  <div className="p-3 bg-dark-900 border border-purple-500/30 rounded-xl space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-purple-400 text-xs font-mono uppercase">2. โหมด DEMO</span>
                      <span className="text-[10px] bg-purple-500/20 text-purple-300 px-1.5 py-0.5 rounded font-bold">พร้อม 100%</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      เชื่อมต่อกับ <b>Binance Futures Testnet</b> ส่งคำสั่งจริง วาง Stop Loss / Take Profit บนเซิร์ฟเวอร์ Binance จริงด้วยเงินทดลอง
                    </p>
                  </div>

                  <div className="p-3 bg-dark-900 border border-amber-500/30 rounded-xl space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-amber-400 text-xs font-mono uppercase">3. โหมด LIVE</span>
                      <span className="text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded font-bold">Fail-Closed 🛡️</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      ระบบเงินจริงเปิดระบบป้องกันความปลอดภัย <b>Fail-Closed</b> ไว้ เพื่อป้องกันไม่ให้ต่อเงินจริงโดยไม่ตั้งใจจนกว่าจะผ่านการซ้อมครบถ้วน
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl space-y-2">
                <div className="flex items-center space-x-2 text-amber-300 font-bold text-xs sm:text-sm">
                  <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
                  <span>ทำไมระบบถึงยังไม่เปิดให้ยิงเงินจริงทันที?</span>
                </div>
                <p className="text-[11px] sm:text-xs text-slate-300 leading-relaxed">
                  ในตลาดคริปโตฟิวเจอร์ส การต่อ API เงินจริงมีความเสี่ยงสูงมาก หากบอทออกคำสั่งผิดพลาดแม้แต่นาทีเดียวอาจส่งผลให้เงินหายได้ ระบบเราจึงใช้กฎความปลอดภัยระดับสูงสุด: <b>"ต้องซ้อมใน PAPER และ Testnet ให้เห็นผลกำไรสม่ำเสมอ และผ่านเกณฑ์ Promotion Gate เสียก่อน จึงจะอนุญาตให้ปลดล็อคเงินจริง"</b>
                </p>
              </div>
            </div>
          )}

          {/* TAB 2: 4-STEP LIVE JOURNEY */}
          {activeTab === 'journey' && (
            <div className="space-y-4">
              <div className="text-xs text-slate-300">
                เส้นทางที่แนะนำในการพาพอร์ตขนาดเล็ก ($10) ก้าวสู่การเทรดอย่างเป็นระบบและปลอดภัย:
              </div>

              <div className="space-y-3">
                {/* Step 1 */}
                <div className="p-3.5 bg-dark-950/70 border border-dark-800 rounded-xl flex items-start space-x-3">
                  <div className="w-6 h-6 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                    1
                  </div>
                  <div className="space-y-1">
                    <div className="font-bold text-white text-xs sm:text-sm flex items-center space-x-2">
                      <span>ซ้อมในโหมด PAPER ด้วยเงินจำลอง $10</span>
                      <span className="text-[10px] bg-dark-800 text-slate-400 px-1.5 py-0.2 rounded font-mono">1-3 วัน</span>
                    </div>
                    <p className="text-slate-400 text-xs leading-relaxed">
                      เข้าเมนู <b>Settings</b> เลือกเงินทุนจำลอง <b>`$10`</b> และเลือกเหรียญเล็ก เช่น <b>`DOGEUSDT, XRPUSDT, SOLUSDT`</b> เพื่อดูว่า AI วิเคราะห์จุดเข้าสวยไหม และเมื่อชนะ/แพ้ พอร์ตได้เสียกี่ดอลลาร์ตามจริง
                    </p>
                  </div>
                </div>

                {/* Step 2 */}
                <div className="p-3.5 bg-dark-950/70 border border-dark-800 rounded-xl flex items-start space-x-3">
                  <div className="w-6 h-6 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                    2
                  </div>
                  <div className="space-y-1">
                    <div className="font-bold text-white text-xs sm:text-sm flex items-center space-x-2">
                      <span>ต่อเข้า Binance Futures Testnet (DEMO)</span>
                      <span className="text-[10px] bg-dark-800 text-slate-400 px-1.5 py-0.2 rounded font-mono">3-7 วัน</span>
                    </div>
                    <p className="text-slate-400 text-xs leading-relaxed">
                      สร้างบัญชีบน <b>testnet.binancefuture.com</b> (ได้รับเหรียญฟรี 15,000 USDT ในระบบจำลอง) นำ Testnet API Key มาใส่ในระบบ เพื่อทดสอบการส่งคำสั่งข้ามเครือข่ายและเช็คการวาง SL/TP บนกระดานจริง
                    </p>
                  </div>
                </div>

                {/* Step 3 */}
                <div className="p-3.5 bg-dark-950/70 border border-dark-800 rounded-xl flex items-start space-x-3">
                  <div className="w-6 h-6 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                    3
                  </div>
                  <div className="space-y-1">
                    <div className="font-bold text-white text-xs sm:text-sm flex items-center space-x-2">
                      <span>ตรวจสอบคะแนนความพร้อม (Promotion Gate Readiness)</span>
                      <span className="text-[10px] bg-dark-800 text-slate-400 px-1.5 py-0.2 rounded font-mono">เกณฑ์วัดผล</span>
                    </div>
                    <p className="text-slate-400 text-xs leading-relaxed">
                      ดูที่หน้า <b>PRO DESK</b> และแถบสถานะด้านบน: ระบบต้องมีอัตรา <b>Win Rate &ge; 55%</b>, <b>Profit Factor &ge; 1.5</b>, และไม่เกิด Max Consecutive Losses เกิน 3 ไม้ติด
                    </p>
                  </div>
                </div>

                {/* Step 4 */}
                <div className="p-3.5 bg-dark-950/70 border border-emerald-500/30 rounded-xl flex items-start space-x-3 bg-emerald-500/5">
                  <div className="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-mono font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                    4
                  </div>
                  <div className="space-y-1">
                    <div className="font-bold text-emerald-300 text-xs sm:text-sm flex items-center space-x-2">
                      <span>ก้าวสู่เงินจริง (LIVE Mode) ด้วยเงินเริ่มต้น $10</span>
                      <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.2 rounded font-mono">เป้าหมายจริง</span>
                    </div>
                    <p className="text-slate-300 text-xs leading-relaxed">
                      โอนเงินจริง $10 USDT เข้ากระเป๋า Binance Futures, สร้าง API Key โดย <b>"ห้ามติ๊กถอนเงิน"</b>, ใส่ API Key ในระบบ แล้วเปิดสวิตช์เริ่มเทรดแบบ Micro Account
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: BINANCE API SETUP */}
          {activeTab === 'api' && (
            <div className="space-y-4">
              <div className="p-4 bg-dark-950/70 border border-dark-800 rounded-xl space-y-3">
                <div className="font-bold text-white text-xs sm:text-sm flex items-center space-x-2">
                  <Key className="w-4 h-4 text-brand-gold" />
                  <span>ขั้นตอนการสร้าง Binance API Key อย่างถูกต้องและปลอดภัย</span>
                </div>

                <ol className="list-decimal list-inside space-y-2 text-xs text-slate-300 leading-relaxed pl-1">
                  <li>
                    เข้าสู่ระบบบนเว็บไซต์ <a href="https://www.binance.com" target="_blank" rel="noopener noreferrer" className="text-cyan-400 underline font-mono">Binance.com</a>
                  </li>
                  <li>
                    ไปที่เมนูโปรไฟล์มุมขวาบน &gt; เลือก <b>API Management (การจัดการ API)</b>
                  </li>
                  <li>
                    กดปุ่ม <b>Create API</b> &gt; เลือกประเภท <b>System generated</b> &gt; ตั้งชื่อ Label เช่น <code className="bg-dark-900 px-1 py-0.5 rounded text-brand-gold">ApexTrader-Bot</code>
                  </li>
                  <li>
                    ผ่านขั้นตอนยืนยันตัวตน 2FA (SMS หรือ Google Authenticator)
                  </li>
                  <li>
                    คัดลอก <b>API Key</b> และ <b>Secret Key</b> เก็บไว้ทันที (Secret Key จะแสดงเพียงครั้งเดียว)
                  </li>
                </ol>
              </div>

              {/* CRITICAL SECURITY RULES */}
              <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl space-y-2.5">
                <div className="flex items-center space-x-2 text-rose-300 font-bold text-xs sm:text-sm">
                  <Lock className="w-4 h-4 shrink-0 text-rose-400" />
                  <span>3 กฎเหล็กความปลอดภัยในการตั้งสิทธิ์ API (สำคัญที่สุด!)</span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex items-start space-x-2 text-slate-200">
                    <span className="text-emerald-400 font-bold">1. ✅ สิทธิ์ที่ต้องติ๊กเปิด:</span>
                    <span>ติ๊กเฉพาะ <b>"Enable Futures" (เปิดใช้งานฟิวเจอร์ส)</b> เท่านั้น</span>
                  </div>

                  <div className="flex items-start space-x-2 text-rose-300 font-bold">
                    <span className="text-rose-400">2. ❌ สิทธิ์ที่ห้ามติ๊กเด็ดขาด:</span>
                    <span>ห้ามติ๊ก <u>"Enable Withdrawals" (อนุญาตให้ถอนเงิน)</u> อย่างเด็ดขาด!</span>
                  </div>
                  <p className="text-[11px] text-slate-400 pl-5">
                    💡 <i>เมื่อปิดสิทธิ์การถอนเงิน แม้ระบบหรือ API Key จะหลุดไปที่ไหน เงินของคุณก็ไม่มีวันถูกโอนออกจากบัญชีได้ 100% บอททำได้เพียงแค่เปิด/ปิดสัญญาเทรดเท่านั้น</i>
                  </p>

                  <div className="flex items-start space-x-2 text-slate-200">
                    <span className="text-amber-400 font-bold">3. 🔒 การจำกัด IP (แนะนำ):</span>
                    <span>หากรันบนเซิร์ฟเวอร์ส่วนตัว ให้เลือก <b>"Restrict access to trusted IPs only"</b> เพื่อความปลอดภัยสูงสุด</span>
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-2">
                {onOpenSettings && (
                  <button
                    onClick={() => {
                      onClose();
                      onOpenSettings();
                    }}
                    className="flex items-center space-x-1.5 px-4 py-2 bg-brand-gold text-dark-950 font-bold text-xs rounded-xl shadow-md hover:bg-amber-400 transition-colors"
                  >
                    <Key className="w-3.5 h-3.5" />
                    <span>ไปที่หน้ากรอก API Key ใน Settings</span>
                  </button>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: $10 STRATEGY */}
          {activeTab === 'strategy' && (
            <div className="space-y-4">
              <div className="p-4 bg-dark-950/70 border border-dark-800 rounded-xl space-y-3">
                <div className="font-bold text-white text-xs sm:text-sm flex items-center space-x-2">
                  <TrendingUp className="w-4 h-4 text-emerald-400" />
                  <span>สูตรการปั้นพอร์ต $10 บนเหรียญ Altcoin (Micro-Capital Blueprint)</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  เงินทุน $10 ถือเป็นพอร์ตขนาด Micro บนกระดานฟิวเจอร์ส ซึ่งมีข้อดีคือ <b>ความเสี่ยงทางการเงินต่ำมาก (ไม่เกิน 350 บาท)</b> แต่ต้องเลือกคู่เหรียญและบริหารเงินให้ถูกต้อง:
                </p>

                <div className="overflow-x-auto">
                  <table className="w-full text-[11px] font-mono border border-dark-800">
                    <thead>
                      <tr className="bg-dark-900 text-slate-400 border-b border-dark-800 text-left">
                        <th className="p-2">คู่เหรียญ</th>
                        <th className="p-2">สัญญาขั้นต่ำ</th>
                        <th className="p-2">Margin (10x)</th>
                        <th className="p-2">เงินเหลือในพอร์ต</th>
                        <th className="p-2">ความเหมาะสม</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-dark-800 text-slate-300">
                      <tr className="bg-emerald-500/5">
                        <td className="p-2 font-bold text-white">DOGEUSDT</td>
                        <td className="p-2">$5 USDT</td>
                        <td className="p-2 text-emerald-400">$0.50</td>
                        <td className="p-2 text-emerald-400">$9.50 (95%)</td>
                        <td className="p-2 text-emerald-300 font-sans">🌟 ดีเยี่ยม ปลอดภัยสูงสุด</td>
                      </tr>
                      <tr className="bg-emerald-500/5">
                        <td className="p-2 font-bold text-white">XRPUSDT</td>
                        <td className="p-2">$5 USDT</td>
                        <td className="p-2 text-emerald-400">$0.50</td>
                        <td className="p-2 text-emerald-400">$9.50 (95%)</td>
                        <td className="p-2 text-emerald-300 font-sans">🌟 ดีเยี่ยม สภาพคล่องสูง</td>
                      </tr>
                      <tr>
                        <td className="p-2 font-bold text-white">SOLUSDT</td>
                        <td className="p-2">~$15 USDT</td>
                        <td className="p-2 text-slate-300">$1.50</td>
                        <td className="p-2 text-slate-300">$8.50 (85%)</td>
                        <td className="p-2 text-slate-400 font-sans">✅ ปานกลาง เทรนด์ชัด</td>
                      </tr>
                      <tr className="bg-rose-500/5">
                        <td className="p-2 font-bold text-rose-300">BTCUSDT</td>
                        <td className="p-2">~$85 USDT</td>
                        <td className="p-2 text-rose-400">$8.50</td>
                        <td className="p-2 text-rose-400">$1.50 (15%)</td>
                        <td className="p-2 text-rose-400 font-sans">❌ ไม่แนะนำสำหรับทุน $10</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div className="pt-2 space-y-1.5 text-xs text-slate-300">
                  <div className="font-bold text-white">เคล็ดลับการทบต้น (Compounding Rule):</div>
                  <ul className="list-disc list-inside space-y-1 text-[11px] text-slate-400">
                    <li>ตั้งความเสี่ยงต่อไม้ไว้ที่ <b>3% – 5%</b> (เสียไม้ละ -$0.30 ถึง -$0.50)</li>
                    <li>เมื่อชนเป้าหมาย Take Profit (RR 1:2) จะได้กำไร <b>+$0.60 ถึง +$1.00</b> ต่อไม้</li>
                    <li>เมื่อพอร์ตโตแตะ $30 - $50 จึงค่อยขยับความเสี่ยงขึ้นเป็นไม้ละ $1.50 - $2.50 ตามลำดับ</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: SAFETY GATES */}
          {activeTab === 'safety' && (
            <div className="space-y-4">
              <div className="p-4 bg-dark-950/70 border border-dark-800 rounded-xl space-y-3">
                <div className="font-bold text-white text-xs sm:text-sm flex items-center space-x-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <span>ระบบความปลอดภัยในตัว (Institutional Guardrails)</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="p-3 bg-dark-900 border border-dark-700/60 rounded-xl space-y-1">
                    <div className="font-bold text-white text-xs">1. Server-Side Protective SL</div>
                    <p className="text-[11px] text-slate-400">
                      ทุกออเดอร์ที่ถูกยิงออกไป จะต้องส่งคำสั่ง Stop Loss ฝั่งกระดานเทรดคู่กันเสมอ ไม่มีคำสั่งไหนถูกเปิดทิ้งไว้โดยไร้การป้องกัน
                    </p>
                  </div>

                  <div className="p-3 bg-dark-900 border border-dark-700/60 rounded-xl space-y-1">
                    <div className="font-bold text-white text-xs">2. Daily Circuit Breaker</div>
                    <p className="text-[11px] text-slate-400">
                      หากวันไหนตลาดผันผวนผิดปกติจนแตะเพดานขาดทุนรายวัน (เช่น 10%) ระบบจะหยุดทำงานอัตโนมัติทันทีเพื่อรักษาเงินต้นที่เหลือ
                    </p>
                  </div>

                  <div className="p-3 bg-dark-900 border border-dark-700/60 rounded-xl space-y-1">
                    <div className="font-bold text-white text-xs">3. Consecutive Loss Limiter</div>
                    <p className="text-[11px] text-slate-400">
                      หากแพ้ติดต่อกัน 3 ไม้ ระบบ Risk Engine จะบล็อกการออกคำสั่งเพื่อไม่ให้เกิดการเทรดแบบใช้อารมณ์ (Revenge Trading)
                    </p>
                  </div>

                  <div className="p-3 bg-dark-900 border border-dark-700/60 rounded-xl space-y-1">
                    <div className="font-bold text-white text-xs">4. PANIC Emergency Kill Switch</div>
                    <p className="text-[11px] text-slate-400">
                      มีปุ่ม <b>PANIC</b> สีแดงที่ Header ตลอดเวลา กดเพียงครั้งเดียวระบบจะยกเลิกทุกคำสั่งค้างและปิดสถานะทั้งหมดในทันที
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-dark-800 bg-dark-950/70 flex items-center justify-between shrink-0">
          <div className="flex items-center space-x-1.5 text-[11px] text-slate-400">
            <Sparkles className="w-3.5 h-3.5 text-brand-gold" />
            <span>ApexTrader AI Terminal — ปฏิบัติตามกฎความปลอดภัยอย่างเคร่งครัด</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-dark-800 hover:bg-dark-700 text-slate-200 hover:text-white text-xs font-semibold rounded-xl border border-dark-700 transition-colors"
          >
            เข้าใจแล้ว ปิดหน้าต่าง
          </button>
        </div>
      </div>
    </div>
  );
};

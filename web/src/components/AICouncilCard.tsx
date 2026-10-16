import React from 'react';
import { Bot, CheckCircle2, XCircle, Eye, ShieldCheck, Zap } from 'lucide-react';
import { CouncilLatest } from '../services/api';

interface AICouncilCardProps {
  data: CouncilLatest | null;
}

export const AICouncilCard: React.FC<AICouncilCardProps> = ({ data }) => {
  const latest = data?.latest;

  if (!latest) {
    return (
      <div className="w-full flex-1 p-6 border-b border-dark-800 bg-dark-900/40 flex flex-col items-center justify-center text-xs text-slate-500 space-y-2">
        <Bot className="w-6 h-6 text-slate-600 animate-pulse" />
        <span>กำลังรอสัญญาณ AI Council...</span>
      </div>
    );
  }

  const isBuy = latest.decision.toUpperCase().includes('BUY');
  const isSell = latest.decision.toUpperCase().includes('SELL');
  const isSkip = latest.decision.toUpperCase().includes('SKIP');

  const badgeColor = isBuy
    ? 'bg-brand-green/15 text-brand-green border-brand-green/30'
    : isSell
    ? 'bg-brand-red/15 text-brand-red border-brand-red/30'
    : 'bg-amber-500/15 text-amber-400 border-amber-500/30';

  return (
    <div className="w-full flex-1 border-t border-dark-800 bg-dark-900/50 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="min-h-[52px] py-1 px-3.5 border-b border-dark-800 flex items-center justify-between bg-dark-900/70 select-none">
        <div className="flex items-center space-x-2">
          <Bot className="w-4 h-4 text-brand-blue" />
          <span className="text-xs font-bold tracking-wider text-slate-200">AI COUNCIL VERDICT</span>
        </div>
        <div className="flex items-center space-x-1 font-mono text-[11px]">
          <span className="text-slate-400">Score:</span>
          <span className="font-bold text-brand-gold">{latest.score}/100</span>
        </div>
      </div>

      {/* Decision Summary */}
      <div className="p-3.5 space-y-3 overflow-y-auto flex-1">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="font-bold text-xs text-white">{latest.symbol}</span>
            <span className="text-[11px] font-mono text-slate-400">({latest.candidate})</span>
          </div>
          <span className={`text-[11px] px-2 py-0.5 rounded font-mono font-bold uppercase border ${badgeColor}`}>
            {latest.decision}
          </span>
        </div>

        {/* Narrative Reason in Thai */}
        <div className="p-2.5 rounded-lg bg-dark-800/80 border border-dark-700/60">
          <div className="text-[10px] text-slate-400 uppercase font-mono mb-1 flex items-center space-x-1">
            <Zap className="w-3 h-3 text-brand-gold" />
            <span>AI Reasoning Analysis</span>
          </div>
          <p className="text-xs text-slate-200 leading-relaxed font-sans">
            {latest.reason}
          </p>
        </div>

        {/* Confluences */}
        {latest.confluences && latest.confluences.length > 0 && (
          <div>
            <div className="text-[10px] text-slate-400 uppercase font-mono mb-1.5">SMC Confluences</div>
            <div className="flex flex-wrap gap-1">
              {latest.confluences.map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] bg-dark-800 text-slate-300 px-1.5 py-0.5 rounded border border-dark-700 font-mono"
                >
                  ✓ {tag.replace('_', ' ')}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Multimodal AI Vision Confirmation */}
        {latest.vision_verdict && (
          <div className="p-2 rounded bg-dark-850 border border-dark-750 flex items-start space-x-2">
            <Eye className="w-3.5 h-3.5 text-brand-blue mt-0.5 shrink-0" />
            <div className="text-[11px]">
              <div className="flex items-center space-x-1 font-semibold text-slate-200">
                <span>Vision Verdict:</span>
                <span className="text-brand-green">
                  {latest.vision_verdict.confirmed ? 'Confirmed' : 'Caution'} ({(latest.vision_verdict.confidence * 100).toFixed(0)}%)
                </span>
              </div>
              <p className="text-[10px] text-slate-400 leading-snug mt-0.5">
                {latest.vision_verdict.rejection_wick || latest.vision_verdict.notes}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

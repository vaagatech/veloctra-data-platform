import React from 'react';
import { CircuitBreakerInfo } from '../types';
import { ZapOff, ShieldAlert, CheckCircle } from 'lucide-react';

interface CircuitBreakerMonitorProps {
  breakers: CircuitBreakerInfo[];
}

export const CircuitBreakerMonitor: React.FC<CircuitBreakerMonitorProps> = ({ breakers }) => {
  const getStateBadge = (state: string) => {
    switch (state) {
      case 'CLOSED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold">
            <CheckCircle className="w-3 h-3" /> CLOSED (Healthy)
          </span>
        );
      case 'OPEN':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 text-xs font-bold animate-pulse">
            <ZapOff className="w-3 h-3" /> OPEN (Tripped)
          </span>
        );
      case 'HALF_OPEN':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 text-xs font-bold">
            <ShieldAlert className="w-3 h-3" /> HALF_OPEN (Probing)
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-3">
      <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider border-b border-slate-100 pb-2">
        Circuit Breakers
      </h3>
      {breakers.length === 0 ? (
        <div className="text-xs text-slate-400 py-6 text-center">No circuit breakers active</div>
      ) : (
        breakers.map((cb) => (
          <div
            key={cb.name}
            className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between hover:bg-slate-100/60 transition-colors"
          >
            <div>
              <div className="text-xs font-bold text-slate-900">{cb.name}</div>
              <div className="text-[11px] text-slate-500 mt-0.5 font-sans">
                Failures: <span className="font-mono font-semibold text-slate-700">{cb.failure_count}</span>
              </div>
            </div>
            {getStateBadge(cb.state)}
          </div>
        ))
      )}
    </div>
  );
};

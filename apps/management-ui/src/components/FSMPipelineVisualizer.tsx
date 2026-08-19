import { FSMState } from '../types';
import { AlertTriangle, ArrowDown, Settings, ArrowUp, Bookmark, Flag } from 'lucide-react';

interface FSMPipelineVisualizerProps {
  currentState: FSMState | null;
}

const STEPS: { name: FSMState; label: string; icon: React.ReactNode }[] = [
  { name: 'CREATED', label: 'Created', icon: <span className="w-2 h-2 rounded-full bg-slate-400" /> },
  { name: 'VALIDATING', label: 'Validating', icon: <Settings className="w-3.5 h-3.5" /> },
  { name: 'EXTRACTING', label: 'Extracting', icon: <ArrowDown className="w-3.5 h-3.5" /> },
  { name: 'TRANSFORMING', label: 'Transforming', icon: <Settings className="w-3.5 h-3.5" /> },
  { name: 'LOADING', label: 'Loading', icon: <ArrowUp className="w-3.5 h-3.5" /> },
  { name: 'CHECKPOINTING', label: 'Checkpointing', icon: <Bookmark className="w-3.5 h-3.5" /> },
  { name: 'COMPLETED', label: 'Completed', icon: <Flag className="w-3.5 h-3.5" /> },
];

export const FSMPipelineVisualizer: React.FC<FSMPipelineVisualizerProps> = ({ currentState }) => {
  const getStepClass = (stepName: FSMState) => {
    if (!currentState) return 'border-slate-700 bg-slate-800/50 text-slate-500';

    const order: FSMState[] = ['CREATED', 'VALIDATING', 'EXTRACTING', 'TRANSFORMING', 'LOADING', 'CHECKPOINTING', 'COMPLETED'];
    const currentIdx = order.indexOf(currentState);
    const stepIdx = order.indexOf(stepName);

    if (currentState === 'FAILED') {
      return stepIdx <= currentIdx
        ? 'border-rose-500 bg-rose-500/20 text-rose-400'
        : 'border-slate-800 bg-slate-900 text-slate-600';
    }

    if (currentState === 'DLQ_ROUTED') {
      return stepName === 'LOADING'
        ? 'border-orange-500 bg-orange-500/20 text-orange-400 shadow-lg shadow-orange-500/30'
        : stepIdx < currentIdx
        ? 'border-emerald-500 bg-emerald-500/20 text-emerald-400'
        : 'border-slate-800 bg-slate-900 text-slate-600';
    }

    if (stepIdx < currentIdx) {
      return 'border-emerald-500 bg-emerald-500/20 text-emerald-400';
    }
    if (stepIdx === currentIdx) {
      return 'border-indigo-500 bg-indigo-500/20 text-indigo-400 shadow-lg shadow-indigo-500/40 animate-pulse';
    }
    return 'border-slate-800 bg-slate-900/60 text-slate-600';
  };

  return (
    <div className="glass-panel rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">FSM State Machine Automaton</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Current execution state: <span className="font-semibold text-slate-100">{currentState || 'None'}</span>
          </p>
        </div>
        {currentState === 'FAILED' && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-medium">
            <AlertTriangle className="w-3.5 h-3.5" /> Pipeline Failed
          </div>
        )}
        {currentState === 'PAUSED' && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-medium">
            Paused
          </div>
        )}
      </div>

      <div className="flex items-center justify-between relative py-3 overflow-x-auto">
        <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-slate-800 -translate-y-1/2 z-0" />
        {STEPS.map((step) => {
          const stepClass = getStepClass(step.name);
          return (
            <div key={step.name} className="flex flex-col items-center gap-2 relative z-10 min-w-[70px]">
              <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center transition-all ${stepClass}`}>
                {step.icon}
              </div>
              <span className="text-[11px] font-medium text-slate-400 whitespace-nowrap">{step.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

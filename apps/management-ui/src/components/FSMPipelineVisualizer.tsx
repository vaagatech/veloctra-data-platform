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
    if (!currentState) return 'border-slate-300 bg-slate-100 text-slate-400';

    const order: FSMState[] = ['CREATED', 'VALIDATING', 'EXTRACTING', 'TRANSFORMING', 'LOADING', 'CHECKPOINTING', 'COMPLETED'];
    const currentIdx = order.indexOf(currentState);
    const stepIdx = order.indexOf(stepName);

    if (currentState === 'FAILED') {
      return stepIdx <= currentIdx
        ? 'border-rose-500 bg-rose-50 text-rose-600 font-bold'
        : 'border-slate-200 bg-slate-50 text-slate-300';
    }

    if (currentState === 'DLQ_ROUTED') {
      return stepName === 'LOADING'
        ? 'border-orange-500 bg-orange-50 text-orange-600 shadow-md shadow-orange-500/20'
        : stepIdx < currentIdx
        ? 'border-emerald-500 bg-emerald-50 text-emerald-600'
        : 'border-slate-200 bg-slate-50 text-slate-300';
    }

    if (stepIdx < currentIdx) {
      return 'border-emerald-500 bg-emerald-50 text-emerald-600 font-bold';
    }
    if (stepIdx === currentIdx) {
      return 'border-indigo-600 bg-indigo-50 text-indigo-600 shadow-md shadow-indigo-500/30 animate-pulse font-bold';
    }
    return 'border-slate-200 bg-slate-50 text-slate-400';
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-bold text-slate-900">FSM State Machine Automaton</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Current execution state: <span className="font-bold text-indigo-600">{currentState || 'None'}</span>
          </p>
        </div>
        {currentState === 'FAILED' && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-50 border border-rose-200 text-rose-700 text-xs font-semibold">
            <AlertTriangle className="w-3.5 h-3.5" /> Pipeline Failed
          </div>
        )}
        {currentState === 'PAUSED' && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-xs font-semibold">
            Paused
          </div>
        )}
      </div>

      <div className="flex items-center justify-between relative py-3 overflow-x-auto">
        <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-slate-200 -translate-y-1/2 z-0" />
        {STEPS.map((step) => {
          const stepClass = getStepClass(step.name);
          return (
            <div key={step.name} className="flex flex-col items-center gap-2 relative z-10 min-w-[70px]">
              <div className={`w-8 h-8 rounded-full border-2 flex items-center justify-center transition-all ${stepClass}`}>
                {step.icon}
              </div>
              <span className="text-[11px] font-semibold text-slate-600 whitespace-nowrap">{step.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

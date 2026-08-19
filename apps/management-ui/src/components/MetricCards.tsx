import React from 'react';
import { Activity, Database, Cpu, Layers } from 'lucide-react';
import { PipelineProgressEvent } from '../types';

interface MetricCardsProps {
  progress: PipelineProgressEvent | null;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ progress }) => {
  const rowsPerSec = progress?.rows_per_sec ?? 0;
  const rowsProcessed = progress?.rows_processed ?? 0;
  const memoryPct = progress?.memory_percent ?? 0;
  const chunkSize = progress?.chunk_size ?? 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Rate Card */}
      <div className="glass-card rounded-xl p-4 relative overflow-hidden group hover:border-indigo-500/50 transition-all">
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-indigo-500 to-purple-500" />
        <div className="flex items-center justify-between text-slate-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">Processing Rate</span>
          <Activity className="w-4 h-4 text-indigo-400" />
        </div>
        <div className="text-2xl font-bold font-mono text-slate-100">
          {rowsPerSec > 0 ? rowsPerSec.toLocaleString() : '—'}
        </div>
        <div className="text-xs text-slate-400 mt-1">Rows / second</div>
      </div>

      {/* Rows Processed Card */}
      <div className="glass-card rounded-xl p-4 relative overflow-hidden group hover:border-emerald-500/50 transition-all">
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-emerald-500" />
        <div className="flex items-center justify-between text-slate-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">Total Rows</span>
          <Database className="w-4 h-4 text-emerald-400" />
        </div>
        <div className="text-2xl font-bold font-mono text-slate-100">
          {rowsProcessed > 0 ? rowsProcessed.toLocaleString() : '—'}
        </div>
        <div className="text-xs text-slate-400 mt-1">Cumulative records</div>
      </div>

      {/* Memory Guard Card */}
      <div className="glass-card rounded-xl p-4 relative overflow-hidden group hover:border-amber-500/50 transition-all">
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-amber-500" />
        <div className="flex items-center justify-between text-slate-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">RAM Usage</span>
          <Cpu className="w-4 h-4 text-amber-400" />
        </div>
        <div className="text-2xl font-bold font-mono text-slate-100">
          {memoryPct > 0 ? `${memoryPct.toFixed(1)}%` : '—'}
        </div>
        <div className="text-xs text-slate-400 mt-1">Adaptive MemoryGuard</div>
      </div>

      {/* Chunk Size Card */}
      <div className="glass-card rounded-xl p-4 relative overflow-hidden group hover:border-orange-500/50 transition-all">
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-orange-500" />
        <div className="flex items-center justify-between text-slate-400 mb-2">
          <span className="text-xs font-semibold uppercase tracking-wider">Chunk Size</span>
          <Layers className="w-4 h-4 text-orange-400" />
        </div>
        <div className="text-2xl font-bold font-mono text-slate-100">
          {chunkSize > 0 ? chunkSize.toLocaleString() : '—'}
        </div>
        <div className="text-xs text-slate-400 mt-1">Adaptive backpressure</div>
      </div>
    </div>
  );
};

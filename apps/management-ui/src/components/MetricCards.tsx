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
      <div className="bg-white rounded-xl border border-slate-200/80 p-4 relative overflow-hidden shadow-sm hover:shadow-md transition-all group">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-indigo-500 to-violet-600" />
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Processing Rate</span>
          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
            <Activity className="w-4 h-4" />
          </div>
        </div>
        <div className="text-2xl font-black font-mono text-slate-900 tracking-tight">
          {rowsPerSec > 0 ? rowsPerSec.toLocaleString() : '—'}
        </div>
        <div className="text-xs font-medium text-slate-500 mt-1">Rows / second</div>
      </div>

      {/* Rows Processed Card */}
      <div className="bg-white rounded-xl border border-slate-200/80 p-4 relative overflow-hidden shadow-sm hover:shadow-md transition-all group">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-500 to-teal-600" />
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Total Rows</span>
          <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600">
            <Database className="w-4 h-4" />
          </div>
        </div>
        <div className="text-2xl font-black font-mono text-slate-900 tracking-tight">
          {rowsProcessed > 0 ? rowsProcessed.toLocaleString() : '—'}
        </div>
        <div className="text-xs font-medium text-slate-500 mt-1">Cumulative records written</div>
      </div>

      {/* Memory Guard Card */}
      <div className="bg-white rounded-xl border border-slate-200/80 p-4 relative overflow-hidden shadow-sm hover:shadow-md transition-all group">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-amber-500 to-orange-500" />
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-500">RAM Usage</span>
          <div className="w-8 h-8 rounded-lg bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600">
            <Cpu className="w-4 h-4" />
          </div>
        </div>
        <div className="text-2xl font-black font-mono text-slate-900 tracking-tight">
          {memoryPct > 0 ? `${memoryPct.toFixed(1)}%` : '—'}
        </div>
        <div className="text-xs font-medium text-slate-500 mt-1">Adaptive MemoryGuard</div>
      </div>

      {/* Chunk Size Card */}
      <div className="bg-white rounded-xl border border-slate-200/80 p-4 relative overflow-hidden shadow-sm hover:shadow-md transition-all group">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-cyan-500 to-blue-600" />
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-500">Chunk Size</span>
          <div className="w-8 h-8 rounded-lg bg-cyan-50 border border-cyan-100 flex items-center justify-center text-cyan-600">
            <Layers className="w-4 h-4" />
          </div>
        </div>
        <div className="text-2xl font-black font-mono text-slate-900 tracking-tight">
          {chunkSize > 0 ? chunkSize.toLocaleString() : '—'}
        </div>
        <div className="text-xs font-medium text-slate-500 mt-1">Adaptive backpressure buffer</div>
      </div>
    </div>
  );
};

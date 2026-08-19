import React from 'react';
import { DLQRecord } from '../types';
import { RotateCw, AlertTriangle, CheckCircle2, Play } from 'lucide-react';

interface DLQInspectorProps {
  records: DLQRecord[];
  onReplay: () => void;
  onRefresh: () => void;
  jobId: string | null;
  token?: string;
}

export const DLQInspector: React.FC<DLQInspectorProps> = ({ records, onReplay, onRefresh, jobId, token }) => {
  const handleReplayRecord = async (recId: number) => {
    if (!jobId) return;
    try {
      await fetch(`/pipelines/${jobId}/dlq/replay-record/${recId}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      onRefresh();
    } catch (err) {
      console.error('Failed to replay single record:', err);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-slate-50">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600" />
          <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Per-Record Dead Letter Queue (DLQ)</h3>
          <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-slate-200 text-slate-700 font-bold font-mono">
            {records.length} records
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            className="p-1.5 rounded-md hover:bg-slate-200/60 text-slate-500 hover:text-slate-900 transition-colors"
            title="Refresh DLQ"
          >
            <RotateCw className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onReplay}
            disabled={!jobId || records.length === 0}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-amber-50 hover:bg-amber-100 border border-amber-200 text-amber-800 text-xs font-semibold disabled:opacity-40 transition-colors"
          >
            <RotateCw className="w-3 h-3" /> Replay All Pending Records
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead className="sticky top-0 bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
            <tr>
              <th className="py-2.5 px-3">ID</th>
              <th className="py-2.5 px-3">Chunk</th>
              <th className="py-2.5 px-3">Failed Record Payload & Trace</th>
              <th className="py-2.5 px-3">Timestamp</th>
              <th className="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
            {records.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-8 text-center text-slate-400 font-sans">
                  No DLQ records found — stream execution clean ✓
                </td>
              </tr>
            ) : (
              records.map((rec) => (
                <tr key={rec.id} className="hover:bg-slate-50 transition-colors">
                  <td className="py-2.5 px-3 text-slate-500 font-semibold">#{rec.id}</td>
                  <td className="py-2.5 px-3 text-slate-700">{rec.chunk_index ?? '—'}</td>
                  <td
                    className="py-2.5 px-3 max-w-[260px] truncate text-rose-700 font-mono font-medium"
                    title={rec.error_trace}
                  >
                    {rec.error_trace.split('\n')[0]}
                  </td>
                  <td className="py-2.5 px-3 text-slate-400 font-sans">
                    {new Date(rec.ts * 1000).toLocaleTimeString()}
                  </td>
                  <td className="py-2.5 px-3 text-right font-sans">
                    {rec.replayed ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold">
                        <CheckCircle2 className="w-2.5 h-2.5" /> Replayed
                      </span>
                    ) : (
                      <button
                        onClick={() => handleReplayRecord(rec.id)}
                        className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 text-[10px] font-bold transition-all"
                        title="Replay individual record"
                      >
                        <Play className="w-2.5 h-2.5" /> Replay Record
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

import React, { useState, useEffect } from 'react';
import { Activity, Cpu, ClipboardList, RotateCw, FileText, Download, TrendingUp, CheckCircle2, Server, HardDrive } from 'lucide-react';
import { PipelineProgressEvent, FSMState } from '../types';

interface ObservabilityDashboardProps {
  progress: PipelineProgressEvent | null;
  currentState: FSMState | null;
  auditLog: any[];
  dlqRecords: any[];
  onRefresh: () => void;
  token?: string;
  projectId?: string;
}

export const ObservabilityDashboard: React.FC<ObservabilityDashboardProps> = ({
  progress,
  currentState,
  auditLog,
  dlqRecords: _dlqRecords,
  onRefresh,
  token,
  projectId = 'finance_prod_workspace',
}) => {
  // Timeframe Filter State
  const [timeframe, setTimeframe] = useState<'5m' | '15m' | '1h' | '24h' | 'custom'>('15m');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');

  // Live System Metrics from GET /metrics/live
  const [liveMetrics, setLiveMetrics] = useState<any>(null);

  // History Metrics State
  const [metricsHistory, setMetricsHistory] = useState<any>(null);
  const [loadingMetrics, setLoadingMetrics] = useState(false);

  // Custom Report Modal State
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [reportTitle, setReportTitle] = useState('Enterprise Data Platform Health Summary');
  const [generatedReport, setGeneratedReport] = useState<any>(null);
  const [generatingReport, setGeneratingReport] = useState(false);

  // Poll live metrics every 2 seconds
  useEffect(() => {
    let isMounted = true;
    const fetchLive = async () => {
      try {
        const res = await fetch('/metrics/live', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok && isMounted) {
          const data = await res.json();
          setLiveMetrics(data);
        }
      } catch (err) {
        console.error('Failed to fetch live metrics:', err);
      }
    };

    fetchLive();
    const interval = setInterval(fetchLive, 2000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [token]);

  const fetchMetricsHistory = async () => {
    setLoadingMetrics(true);
    try {
      let url = `/metrics/history?timeframe=${timeframe}&project_id=${projectId}`;
      if (timeframe === 'custom' && customFrom && customTo) {
        const fromTs = new Date(customFrom).getTime() / 1000;
        const toTs = new Date(customTo).getTime() / 1000;
        url += `&from_ts=${fromTs}&to_ts=${toTs}`;
      }

      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setMetricsHistory(data);
      }
    } catch (err) {
      console.error('Failed to fetch metrics history:', err);
    } finally {
      setLoadingMetrics(false);
    }
  };

  useEffect(() => {
    fetchMetricsHistory();
  }, [timeframe, projectId]);

  const handleGenerateReport = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneratingReport(true);
    try {
      const res = await fetch('/reports/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          title: reportTitle,
          timeframe: timeframe,
          project_id: projectId,
          include_dlq_summary: true,
          include_throughput_chart: true,
          include_audit_trail: true,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setGeneratedReport(data);
      }
    } catch (err) {
      console.error('Report generation error:', err);
    } finally {
      setGeneratingReport(false);
    }
  };

  const rowsProcessed = progress?.rows_processed ?? 0;
  const rowsPerSec = progress?.rows_per_sec ?? (liveMetrics?.system?.cpu_percent ? 0 : 0);
  const memoryPct = liveMetrics?.system?.memory_percent ?? progress?.memory_percent ?? 0;
  const cpuPct = liveMetrics?.system?.cpu_percent ?? 0;
  const cpuCores = liveMetrics?.system?.cpu_cores ?? 8;
  const memUsedGb = liveMetrics?.system?.memory_used_gb ?? (liveMetrics?.system?.memory_total_mb ? ((liveMetrics.system.memory_total_mb - liveMetrics.system.memory_available_mb) / 1024).toFixed(2) : '0.00');
  const memTotalGb = liveMetrics?.system?.memory_total_gb ?? (liveMetrics?.system?.memory_total_mb ? (liveMetrics.system.memory_total_mb / 1024).toFixed(2) : '8.00');
  const memAvailableGb = liveMetrics?.system?.memory_available_gb ?? (liveMetrics?.system?.memory_available_mb ? (liveMetrics.system.memory_available_mb / 1024).toFixed(2) : '0.00');
  const threadCount = liveMetrics?.process?.threads_count ?? 16;
  const procRssMb = liveMetrics?.process?.rss_mb ?? 0;
  const gcCounts = liveMetrics?.gc_stats?.counts ?? [0, 0, 0];
  const stateBackend = liveMetrics?.state_backend?.type ?? 'mongodb';

  const datapoints = metricsHistory?.datapoints || [];

  return (
    <div className="space-y-6">
      {/* Top Controls & Timeframe Selector */}
      <div className="bg-slate-900/90 p-4 rounded-xl border border-slate-800 shadow-xl flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              Deep Telemetry & Observability Center
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono font-medium">
                Live State: {stateBackend.toUpperCase()}
              </span>
            </h2>
            <p className="text-xs text-slate-400">Real-time hardware utilization, MemoryGuard limits, and time-series throughput streaming</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Timeframe selector buttons */}
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            {(['5m', '15m', '1h', '24h', 'custom'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-3 py-1 rounded-md font-bold transition-all ${
                  timeframe === tf ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tf === 'custom' ? 'Custom' : `Last ${tf}`}
              </button>
            ))}
          </div>

          {timeframe === 'custom' && (
            <div className="flex items-center gap-1.5 text-xs">
              <input
                type="datetime-local"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
                className="px-2 py-1 bg-slate-950 border border-slate-700 rounded text-slate-200 text-[11px]"
              />
              <span className="text-slate-500">to</span>
              <input
                type="datetime-local"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
                className="px-2 py-1 bg-slate-950 border border-slate-700 rounded text-slate-200 text-[11px]"
              />
            </div>
          )}

          <button
            onClick={() => setIsReportModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-bold shadow-md transition-all"
          >
            <FileText className="w-3.5 h-3.5" /> Generate Report
          </button>
        </div>
      </div>

      {/* 4 Deep Hardware & Execution Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* CPU Hardware Gauge */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-4 shadow-lg relative overflow-hidden">
          <div className={`absolute top-0 left-0 right-0 h-1 ${cpuPct > 75 ? 'bg-rose-500' : 'bg-cyan-500'}`} />
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">CPU Utilization</span>
            <Cpu className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-100">{cpuPct}%</div>
            <span className="text-xs text-slate-400">({cpuCores} cores)</span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-1.5 mt-3 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${cpuPct > 75 ? 'bg-rose-500' : 'bg-cyan-500'}`}
              style={{ width: `${Math.min(cpuPct, 100)}%` }}
            />
          </div>
          <div className="text-[11px] text-slate-400 mt-2 flex justify-between">
            <span>Limit: 75.0%</span>
            <span className={cpuPct <= 75 ? 'text-emerald-400' : 'text-rose-400'}>
              {cpuPct <= 75 ? '✓ Governed' : '⚠ Backpressure'}
            </span>
          </div>
        </div>

        {/* RAM Hardware & MemoryGuard Gauge */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-4 shadow-lg relative overflow-hidden">
          <div className={`absolute top-0 left-0 right-0 h-1 ${memoryPct > 75 ? 'bg-amber-500' : 'bg-emerald-500'}`} />
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">RAM MemoryGuard</span>
            <HardDrive className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-100">{memoryPct}%</div>
            <span className="text-xs text-slate-400">({memUsedGb} / {memTotalGb} GB)</span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-1.5 mt-3 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${memoryPct > 75 ? 'bg-amber-500' : 'bg-emerald-500'}`}
              style={{ width: `${Math.min(memoryPct, 100)}%` }}
            />
          </div>
          <div className="text-[11px] text-slate-400 mt-2 flex justify-between">
            <span>Free: {memAvailableGb} GB</span>
            <span className="text-slate-300">Process: {procRssMb} MB</span>
          </div>
        </div>

        {/* Runtime Threads & GC Stats */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-4 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-purple-500" />
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">Runtime & Threads</span>
            <Server className="w-4 h-4 text-purple-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-100">{threadCount}</div>
            <span className="text-xs text-slate-400">Active OS Threads</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-3 flex justify-between font-mono">
            <span>GC Gen Counts:</span>
            <span className="text-purple-300">[{gcCounts.join(', ')}]</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-1 flex justify-between">
            <span>Event Loop:</span>
            <span className="text-emerald-400 font-semibold">Active (AsyncIO)</span>
          </div>
        </div>

        {/* Live Ingestion & Migration Rate */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-4 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-indigo-500" />
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">Live Throughput</span>
            <Activity className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-100">{rowsPerSec.toLocaleString()}</div>
            <span className="text-xs text-slate-400">rows / sec</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-3 flex justify-between">
            <span>Total Ingested:</span>
            <span className="text-indigo-300 font-mono font-bold">{rowsProcessed.toLocaleString()}</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-1 flex justify-between">
            <span>Engine State:</span>
            <span className="text-cyan-400 font-mono">{currentState || 'IDLE / READY'}</span>
          </div>
        </div>
      </div>

      {/* Live Time-Series Throughput Chart */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-5 shadow-xl space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-cyan-400" /> Live Throughput & Chunk Latency Sparkline ({timeframe} window)
          </h3>
          <span className="text-xs text-slate-400 font-mono">
            {loadingMetrics ? 'Fetching history...' : `${datapoints.length} points recorded`}
          </span>
        </div>

        {datapoints.length > 0 ? (
          <div className="h-48 flex items-end gap-1.5 pt-6 pb-2 px-2 bg-slate-950 rounded-lg border border-slate-800/80 overflow-x-auto">
            {datapoints.map((dp: any, idx: number) => {
              const maxThroughput = Math.max(...datapoints.map((d: any) => d.rows_per_sec), 10000);
              const heightPct = Math.min(100, Math.max(12, (dp.rows_per_sec / maxThroughput) * 100));
              return (
                <div key={idx} className="flex-1 flex flex-col items-center gap-1 group relative min-w-[20px]">
                  {/* Tooltip */}
                  <div className="hidden group-hover:block absolute bottom-full mb-2 p-2.5 bg-slate-900 border border-slate-700 text-slate-100 rounded-lg text-[10px] font-mono z-30 whitespace-nowrap shadow-2xl">
                    <div className="text-cyan-400 font-bold">Timestamp: {dp.time_label}</div>
                    <div>Throughput: {dp.rows_per_sec.toLocaleString()} rows/s</div>
                    <div>RAM Usage: {dp.memory_percent}%</div>
                    <div>Chunk Latency: {dp.chunk_latency_ms}ms</div>
                    <div>Connections: {dp.active_connections}</div>
                  </div>

                  <div
                    className="w-full rounded-t bg-gradient-to-t from-cyan-600 to-indigo-500 group-hover:from-cyan-400 group-hover:to-emerald-400 transition-all shadow-sm"
                    style={{ height: `${heightPct}%` }}
                  />
                  <span className="text-[9px] font-mono text-slate-500 truncate max-w-full">{dp.time_label.slice(0, 5)}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="h-48 flex items-center justify-center bg-slate-950 rounded-lg border border-slate-800 text-slate-400 text-xs font-mono">
            No historical data points in the selected window. Run a pipeline to stream telemetry metrics.
          </div>
        )}
      </div>

      {/* Audit Log & Telemetry Table */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-5 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-100">Audit Trail & FSM State Transition Log</h3>
          </div>
          <button
            onClick={onRefresh}
            className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
            title="Refresh Audit Log"
          >
            <RotateCw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-950 text-slate-300 font-semibold border-b border-slate-800">
                <th className="py-2.5 px-3">State Transition</th>
                <th className="py-2.5 px-3">Workspace Tenant</th>
                <th className="py-2.5 px-3">Job Run ID</th>
                <th className="py-2.5 px-3">Metadata Context</th>
                <th className="py-2.5 px-3">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
              {auditLog.length > 0 ? (
                auditLog.map((ev, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-2 px-3 flex items-center gap-1.5 font-bold">
                      <span className="text-slate-400">{ev.from_state}</span>
                      <span className="text-cyan-400">→</span>
                      <span className="text-emerald-400">{ev.to_state}</span>
                    </td>
                    <td className="py-2 px-3 text-slate-300">{ev.tenant_id}</td>
                    <td className="py-2 px-3 text-indigo-400 font-bold">{ev.job_id}</td>
                    <td className="py-2 px-3 text-slate-400 max-w-xs truncate">
                      {typeof ev.metadata === 'object' ? JSON.stringify(ev.metadata) : ev.metadata || '-'}
                    </td>
                    <td className="py-2 px-3 text-slate-400">
                      {typeof ev.created_at === 'number' ? new Date(ev.created_at * 1000).toLocaleTimeString() : ev.created_at}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="py-4 text-center text-slate-500 font-sans">
                    No state transition events recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Report Generation Modal */}
      {isReportModalOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl space-y-4 p-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <FileText className="w-5 h-5 text-indigo-400" /> Export System Health Report
              </h3>
              <button
                onClick={() => {
                  setIsReportModalOpen(false);
                  setGeneratedReport(null);
                }}
                className="text-slate-400 hover:text-slate-200"
              >
                ✕
              </button>
            </div>

            {!generatedReport ? (
              <form onSubmit={handleGenerateReport} className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-300 mb-1">Report Title</label>
                  <input
                    type="text"
                    value={reportTitle}
                    onChange={(e) => setReportTitle(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-slate-100 text-xs focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 text-xs text-slate-400 space-y-1">
                  <div>• Timeframe Window: <span className="text-slate-200 font-bold">{timeframe}</span></div>
                  <div>• Target Workspace: <span className="text-slate-200 font-bold">{projectId}</span></div>
                  <div>• Includes DLQ Failure breakdown, Throughput summary, and FSM audit log.</div>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsReportModalOpen(false)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-bold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={generatingReport}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-bold flex items-center gap-1.5"
                  >
                    {generatingReport ? 'Compiling Report...' : 'Generate Executive Report'}
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4">
                <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-xs text-emerald-400 flex items-center gap-2 font-bold">
                  <CheckCircle2 className="w-4 h-4" /> Report compiled successfully ({generatedReport.generated_at})
                </div>

                <div className="max-h-60 overflow-y-auto p-3 bg-slate-950 border border-slate-800 rounded-lg font-mono text-xs text-slate-300">
                  <pre>{JSON.stringify(generatedReport, null, 2)}</pre>
                </div>

                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => {
                      const blob = new Blob([JSON.stringify(generatedReport, null, 2)], { type: 'application/json' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `etl_report_${Date.now()}.json`;
                      a.click();
                    }}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold flex items-center gap-1.5"
                  >
                    <Download className="w-3.5 h-3.5" /> Download JSON
                  </button>
                  <button
                    onClick={() => {
                      setIsReportModalOpen(false);
                      setGeneratedReport(null);
                    }}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-bold"
                  >
                    Close
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

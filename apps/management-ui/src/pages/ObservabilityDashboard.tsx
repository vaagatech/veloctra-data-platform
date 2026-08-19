import React, { useState, useEffect } from 'react';
import {
  Activity,
  Cpu,
  ClipboardList,
  RotateCw,
  FileText,
  Download,
  TrendingUp,
  CheckCircle2,
  Server,
  HardDrive,
  AlertOctagon,
  AlertCircle,
  Copy,
  Check,
  Maximize2,
  Terminal,
  X,
} from 'lucide-react';
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
  projectId = 'healthcare_prod_workspace',
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

  // Diagnostic Error Modal State
  const [selectedErrorModal, setSelectedErrorModal] = useState<{
    job_id: string;
    from_state: string;
    to_state: string;
    error_message: string;
    traceback?: string;
    metadata?: any;
    timestamp?: number | string;
  } | null>(null);
  const [copiedAuditError, setCopiedAuditError] = useState(false);

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

  const failedEvent = auditLog.find(
    (ev) =>
      ev.to_state === 'FAILED' ||
      (typeof ev.metadata === 'object' && ev.metadata?.error) ||
      (typeof ev.metadata === 'string' && ev.metadata.includes('error'))
  );
  const failedMeta = failedEvent
    ? typeof failedEvent.metadata === 'object'
      ? failedEvent.metadata
      : typeof failedEvent.metadata === 'string'
      ? (() => {
          try {
            return JSON.parse(failedEvent.metadata);
          } catch {
            return { error: failedEvent.metadata };
          }
        })()
      : {}
    : null;

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

      {/* Active / Recent Pipeline Failure Diagnostic Center */}
      {(currentState === 'FAILED' || failedEvent) && (
        <div className="bg-gradient-to-r from-rose-950/95 via-red-950/85 to-slate-900 border-2 border-rose-600/70 rounded-xl p-5 shadow-xl relative overflow-hidden text-slate-100 animate-in fade-in duration-200">
          <div className="absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r from-rose-500 via-red-500 to-amber-500" />
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex items-start gap-3.5 flex-1 min-w-[280px]">
              <div className="w-10 h-10 rounded-xl bg-rose-500/20 border border-rose-500/40 flex items-center justify-center text-rose-400 shrink-0 mt-0.5 shadow-inner">
                <AlertOctagon className="w-5 h-5 text-rose-400 animate-pulse" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="px-2.5 py-0.5 rounded-full bg-rose-500/30 border border-rose-500/60 text-rose-300 font-black text-xs tracking-wider uppercase flex items-center gap-1">
                    <AlertCircle className="w-3 h-3 text-rose-400" /> State Machine Execution Failure
                  </span>
                  {failedEvent && (
                    <span className="px-2.5 py-0.5 rounded-md bg-slate-900 border border-slate-700 text-slate-300 font-mono text-xs">
                      Failed At Transition: <strong className="text-amber-400 font-bold">{failedEvent.from_state} → {failedEvent.to_state}</strong>
                    </span>
                  )}
                  {failedEvent?.job_id && (
                    <span className="px-2 py-0.5 rounded bg-indigo-950 border border-indigo-800 text-indigo-300 font-mono text-xs font-bold">
                      Job: {failedEvent.job_id}
                    </span>
                  )}
                </div>

                <div className="mt-2 text-sm font-semibold text-rose-100 break-words leading-relaxed">
                  {failedMeta?.error || failedMeta?.message || 'Pipeline state machine recorded an execution failure.'}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0 pt-1">
              <button
                onClick={() => {
                  const trace = failedMeta?.traceback || failedMeta?.error || JSON.stringify(failedMeta, null, 2);
                  navigator.clipboard.writeText(trace);
                  setCopiedAuditError(true);
                  setTimeout(() => setCopiedAuditError(false), 2000);
                }}
                className="px-3 py-2 rounded-lg bg-slate-800/90 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-bold flex items-center gap-1.5 shadow-sm transition-colors"
              >
                {copiedAuditError ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedAuditError ? 'Copied' : 'Copy Trace'}
              </button>

              <button
                onClick={() => {
                  if (failedEvent) {
                    setSelectedErrorModal({
                      job_id: failedEvent.job_id,
                      from_state: failedEvent.from_state,
                      to_state: failedEvent.to_state,
                      error_message: failedMeta?.error || failedMeta?.message || 'Pipeline Execution Failure',
                      traceback: failedMeta?.traceback || failedMeta?.error || JSON.stringify(failedMeta, null, 2),
                      metadata: failedMeta,
                      timestamp: failedEvent.created_at,
                    });
                  }
                }}
                className="px-3.5 py-2 rounded-lg bg-rose-900/60 hover:bg-rose-900 border border-rose-600 text-white text-xs font-bold flex items-center gap-1.5 shadow transition-colors"
              >
                <Maximize2 className="w-3.5 h-3.5" /> Full Root Cause Trace
              </button>
            </div>
          </div>
        </div>
      )}

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

        {/* RAM Hardware Gauge */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-4 shadow-lg relative overflow-hidden">
          <div className={`absolute top-0 left-0 right-0 h-1 ${memoryPct > 80 ? 'bg-rose-500' : 'bg-indigo-500'}`} />
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">RAM Allocation</span>
            <Activity className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-100">{memoryPct}%</div>
            <span className="text-xs text-slate-400">({memUsedGb} / {memTotalGb} GB)</span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-1.5 mt-3 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${memoryPct > 80 ? 'bg-rose-500' : 'bg-indigo-500'}`}
              style={{ width: `${Math.min(memoryPct, 100)}%` }}
            />
          </div>
          <div className="text-[11px] text-slate-400 mt-2 flex justify-between">
            <span>Avail: {memAvailableGb} GB</span>
            <span className={memoryPct <= 80 ? 'text-emerald-400' : 'text-rose-400'}>
              {memoryPct <= 80 ? '✓ MemoryGuard Normal' : '⚠ Guard Activated'}
            </span>
          </div>
        </div>

        {/* Process Memory / Threads */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-4 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-emerald-500" />
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">Process Footprint</span>
            <Server className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-100">{procRssMb} MB</div>
            <span className="text-xs text-slate-400">RSS</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-4 space-y-1">
            <div className="flex justify-between">
              <span>Active Threads:</span>
              <span className="text-slate-200 font-mono font-bold">{threadCount}</span>
            </div>
            <div className="flex justify-between">
              <span>GC Cycles (0/1/2):</span>
              <span className="text-slate-200 font-mono">{gcCounts.join('/')}</span>
            </div>
          </div>
        </div>

        {/* Throughput & Buffer */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-4 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-amber-500" />
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">ETL Stream Speed</span>
            <HardDrive className="w-4 h-4 text-amber-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-amber-400">
              {rowsPerSec.toLocaleString()}
            </div>
            <span className="text-xs text-slate-400">rows / sec</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-4 space-y-1">
            <div className="flex justify-between">
              <span>Total Processed:</span>
              <span className="text-slate-200 font-mono font-bold">{rowsProcessed.toLocaleString()} rows</span>
            </div>
            <div className="flex justify-between">
              <span>FSM Execution State:</span>
              <span className="text-emerald-400 font-mono font-bold">{currentState || 'IDLE'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Historical Throughput Chart & Metrics Stream */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-5 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-bold text-slate-100">Telemetry History & Throughput Trend</h3>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-2">
            <span>Granularity: 10s intervals</span>
            {loadingMetrics && <span className="text-indigo-400 animate-pulse font-mono">Syncing...</span>}
          </div>
        </div>

        {datapoints.length > 0 ? (
          <div className="h-48 flex items-end gap-1.5 pt-6 pb-2 px-2 bg-slate-950/80 rounded-lg border border-slate-800/80 overflow-x-auto">
            {datapoints.map((pt: any, idx: number) => {
              const maxVal = Math.max(...datapoints.map((p: any) => p.throughput_rows_sec || 100), 100);
              const heightPct = Math.min(Math.max(((pt.throughput_rows_sec || 0) / maxVal) * 100, 4), 100);
              return (
                <div
                  key={idx}
                  className="flex-1 min-w-[20px] flex flex-col items-center gap-1 group relative h-full justify-end"
                >
                  <div
                    style={{ height: `${heightPct}%` }}
                    className="w-full bg-gradient-to-t from-indigo-600 to-cyan-400 rounded-t-sm hover:brightness-125 transition-all cursor-pointer"
                  />
                  {/* Tooltip on hover */}
                  <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute bottom-full mb-2 bg-slate-800 border border-slate-700 text-[10px] text-slate-200 p-2 rounded shadow-2xl z-20 pointer-events-none whitespace-nowrap">
                    <div>{pt.timestamp}</div>
                    <div className="font-bold text-cyan-300">{pt.throughput_rows_sec || 0} rows/sec</div>
                    <div>RAM: {pt.memory_percent || 0}%</div>
                    <div>CPU: {pt.cpu_percent || 0}%</div>
                  </div>
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
                <th className="py-2.5 px-3">Metadata Context / Diagnostic Reason</th>
                <th className="py-2.5 px-3">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
              {auditLog.length > 0 ? (
                auditLog.map((ev, idx) => {
                  const isFailed =
                    ev.to_state === 'FAILED' ||
                    (typeof ev.metadata === 'object' && ev.metadata?.error) ||
                    (typeof ev.metadata === 'string' && ev.metadata.includes('error'));
                  const meta =
                    typeof ev.metadata === 'object'
                      ? ev.metadata
                      : typeof ev.metadata === 'string'
                      ? (() => {
                          try {
                            return JSON.parse(ev.metadata);
                          } catch {
                            return { raw: ev.metadata };
                          }
                        })()
                      : {};
                  const errMsg = meta.error || meta.message || (isFailed ? 'Runtime execution failure' : null);

                  return (
                    <tr
                      key={idx}
                      className={`transition-colors ${
                        isFailed
                          ? 'bg-rose-950/40 hover:bg-rose-900/50 border-l-4 border-rose-500 text-rose-200'
                          : 'hover:bg-slate-800/40'
                      }`}
                    >
                      <td className="py-2.5 px-3 flex items-center gap-1.5 font-bold">
                        <span className="text-slate-400">{ev.from_state}</span>
                        <span className="text-cyan-400">→</span>
                        {ev.to_state === 'FAILED' ? (
                          <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-bold border border-rose-500/40 text-[11px] flex items-center gap-1 animate-pulse">
                            <AlertCircle className="w-3 h-3 text-rose-400" /> FAILED
                          </span>
                        ) : (
                          <span className="text-emerald-400">{ev.to_state}</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-slate-300">{ev.tenant_id}</td>
                      <td className="py-2.5 px-3 text-indigo-400 font-bold">{ev.job_id}</td>
                      <td className="py-2.5 px-3 max-w-sm">
                        {isFailed ? (
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-rose-300 font-sans font-medium text-xs">
                              {errMsg}
                            </span>
                            <button
                              onClick={() =>
                                setSelectedErrorModal({
                                  job_id: ev.job_id,
                                  from_state: ev.from_state,
                                  to_state: ev.to_state,
                                  error_message: errMsg || 'Pipeline Execution Failure',
                                  traceback: meta.traceback || meta.error || JSON.stringify(meta, null, 2),
                                  metadata: meta,
                                  timestamp: ev.created_at,
                                })
                              }
                              className="px-2.5 py-1 rounded bg-rose-800 hover:bg-rose-700 text-white font-bold text-[10px] shrink-0 flex items-center gap-1 shadow-sm transition-colors"
                            >
                              <Maximize2 className="w-3 h-3" /> Inspect Trace
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-400 truncate block">
                            {typeof ev.metadata === 'object' ? JSON.stringify(ev.metadata) : ev.metadata || '-'}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400">
                        {typeof ev.created_at === 'number' ? new Date(ev.created_at * 1000).toLocaleTimeString() : ev.created_at}
                      </td>
                    </tr>
                  );
                })
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

      {/* Audit Failure Inspection Modal */}
      {selectedErrorModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl space-y-4 p-6 text-slate-100 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-bold text-rose-400 flex items-center gap-2">
                <AlertOctagon className="w-5 h-5 text-rose-500" /> State Transition Failure Root Cause — {selectedErrorModal.job_id}
              </h3>
              <button
                onClick={() => setSelectedErrorModal(null)}
                className="text-slate-400 hover:text-slate-200 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 flex-1 overflow-y-auto pr-1">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <div className="text-slate-500 font-bold uppercase text-[10px]">Transition</div>
                  <div className="text-rose-300 font-mono font-bold mt-1">
                    {selectedErrorModal.from_state} → {selectedErrorModal.to_state}
                  </div>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800">
                  <div className="text-slate-500 font-bold uppercase text-[10px]">Job Run ID</div>
                  <div className="text-indigo-300 font-mono font-bold mt-1 truncate">{selectedErrorModal.job_id}</div>
                </div>
                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 col-span-2 sm:col-span-1">
                  <div className="text-slate-500 font-bold uppercase text-[10px]">Timestamp</div>
                  <div className="text-slate-300 font-mono font-bold mt-1">
                    {typeof selectedErrorModal.timestamp === 'number'
                      ? new Date(selectedErrorModal.timestamp * 1000).toLocaleTimeString()
                      : selectedErrorModal.timestamp}
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-400 mb-1">Error Message</label>
                <div className="p-3 bg-rose-950/40 border border-rose-800/60 rounded-lg text-rose-200 text-xs font-mono break-words leading-relaxed">
                  {selectedErrorModal.error_message}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-bold text-slate-400 flex items-center gap-1.5">
                    <Terminal className="w-3.5 h-3.5 text-slate-500" /> Complete Traceback & Execution Context
                  </label>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(selectedErrorModal.traceback || selectedErrorModal.error_message);
                      setCopiedAuditError(true);
                      setTimeout(() => setCopiedAuditError(false), 2000);
                    }}
                    className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold flex items-center gap-1"
                  >
                    {copiedAuditError ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                    {copiedAuditError ? 'Copied' : 'Copy Trace'}
                  </button>
                </div>
                <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg font-mono text-xs text-slate-300 max-h-72 overflow-y-auto whitespace-pre-wrap leading-relaxed select-text">
                  {selectedErrorModal.traceback || selectedErrorModal.error_message}
                </div>
              </div>

              {selectedErrorModal.metadata && (
                <div>
                  <label className="block text-xs font-bold text-slate-400 mb-1">Full Transition Metadata JSON</label>
                  <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg font-mono text-[11px] text-slate-400 max-h-36 overflow-y-auto">
                    <pre>{JSON.stringify(selectedErrorModal.metadata, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-800 pt-3">
              <button
                onClick={() => setSelectedErrorModal(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-bold transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

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

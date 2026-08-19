import React, { useState, useEffect, useMemo } from 'react';
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
  Layers,
  Filter,
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
  jobs?: any[];
  selectedJobId?: string | null;
  onSelectJob?: (jobId: string) => void;
}

interface PipelineStatusDetail {
  job_id: string;
  state: string;
  metrics?: {
    rows_processed?: number;
    chunks_processed?: number;
    rows_per_sec?: number;
    memory_percent?: number;
    chunk_size?: number;
    duration_sec?: number;
    timestamp?: number;
  };
  latest_checkpoint?: any;
  error?: {
    message?: string;
    traceback?: string;
    error_type?: string;
    failed_at_state?: string;
  };
  circuit_breakers?: Record<string, any>;
}

export const ObservabilityDashboard: React.FC<ObservabilityDashboardProps> = ({
  progress,
  currentState: _currentState,
  auditLog,
  dlqRecords: _dlqRecords,
  onRefresh,
  token,
  projectId = 'healthcare_prod_workspace',
  jobs = [],
  selectedJobId,
  onSelectJob,
}) => {
  // Timeframe Filter State
  const [timeframe, setTimeframe] = useState<'5m' | '15m' | '1h' | '24h' | 'custom'>('15m');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');

  // Pipeline Filter (all vs specific pipeline ID)
  const [selectedPipelineFilter, setSelectedPipelineFilter] = useState<string>(selectedJobId || 'all');

  // REST-based Pipeline Detailed Statuses
  const [pipelineDetails, setPipelineDetails] = useState<Record<string, PipelineStatusDetail>>({});
  const [loadingStatuses, setLoadingStatuses] = useState(false);

  // Live System Metrics from GET /metrics/live
  const [liveMetrics, setLiveMetrics] = useState<any>(null);

  // History Metrics State
  const [metricsHistory, setMetricsHistory] = useState<any>(null);
  const [loadingMetrics, setLoadingMetrics] = useState(false);

  // Custom Report Modal State
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [reportTitle, setReportTitle] = useState('Enterprise Data Platform Fleet Health Summary');
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

  // Fetch all pipeline statuses via REST
  const fetchAllPipelineStatuses = async () => {
    try {
      setLoadingStatuses(true);
      const listRes = await fetch(`/pipelines?tenant_id=${projectId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!listRes.ok) return;

      const listData = await listRes.json();
      const rawJobs = listData.job_list || [];

      const statusMap: Record<string, PipelineStatusDetail> = {};
      await Promise.all(
        rawJobs.map(async (j: any) => {
          try {
            const sRes = await fetch(`/pipelines/${j.id}/status`, {
              headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (sRes.ok) {
              const sData = await sRes.json();
              statusMap[j.id] = sData;
            } else {
              statusMap[j.id] = { job_id: j.id, state: j.state };
            }
          } catch {
            statusMap[j.id] = { job_id: j.id, state: j.state };
          }
        })
      );

      setPipelineDetails(statusMap);
    } catch (err) {
      console.error('Failed to fetch pipeline statuses:', err);
    } finally {
      setLoadingStatuses(false);
    }
  };

  useEffect(() => {
    fetchAllPipelineStatuses();
  }, [projectId, token]);

  // Poll live metrics every 2.5 seconds
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
    const interval = setInterval(fetchLive, 2500);
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
        // Augment generated report with pipeline matrix details
        data.pipeline_fleet = Object.values(pipelineDetails);
        setGeneratedReport(data);
      }
    } catch (err) {
      console.error('Report generation error:', err);
    } finally {
      setGeneratingReport(false);
    }
  };

  // Filtered pipelines list
  const pipelineList = useMemo(() => {
    const fromProps = jobs && jobs.length > 0 ? jobs : [];
    const fromDetails = Object.keys(pipelineDetails).map((id) => ({
      id,
      state: pipelineDetails[id].state,
    }));
    const map = new Map();
    [...fromProps, ...fromDetails].forEach((item) => map.set(item.id, item));
    return Array.from(map.values());
  }, [jobs, pipelineDetails]);

  // Aggregate or single-pipeline metrics calculation
  const activeDetail = selectedPipelineFilter !== 'all' ? pipelineDetails[selectedPipelineFilter] : null;

  const totalAggregatedRows = useMemo(() => {
    if (selectedPipelineFilter !== 'all' && activeDetail) {
      return activeDetail.metrics?.rows_processed ?? 0;
    }
    return Object.values(pipelineDetails).reduce((sum, p) => sum + (p.metrics?.rows_processed || 0), 0) || (progress?.rows_processed ?? 0);
  }, [selectedPipelineFilter, activeDetail, pipelineDetails, progress]);

  const effectiveThroughput = useMemo(() => {
    if (selectedPipelineFilter !== 'all' && activeDetail) {
      return activeDetail.metrics?.rows_per_sec ?? 0;
    }
    return Object.values(pipelineDetails).reduce((sum, p) => sum + (p.metrics?.rows_per_sec || 0), 0) || (progress?.rows_per_sec ?? 0);
  }, [selectedPipelineFilter, activeDetail, pipelineDetails, progress]);

  const memoryPct = liveMetrics?.system?.memory_percent ?? progress?.memory_percent ?? 84.9;
  const cpuPct = liveMetrics?.system?.cpu_percent ?? 0;
  const cpuCores = liveMetrics?.system?.cpu_cores ?? 8;
  const memUsedGb = liveMetrics?.system?.memory_used_gb ?? (liveMetrics?.system?.memory_total_mb ? ((liveMetrics.system.memory_total_mb - liveMetrics.system.memory_available_mb) / 1024).toFixed(2) : '6.79');
  const memTotalGb = liveMetrics?.system?.memory_total_gb ?? (liveMetrics?.system?.memory_total_mb ? (liveMetrics.system.memory_total_mb / 1024).toFixed(2) : '8.00');
  const memAvailableGb = liveMetrics?.system?.memory_available_gb ?? (liveMetrics?.system?.memory_available_mb ? (liveMetrics.system.memory_available_mb / 1024).toFixed(2) : '1.21');
  const threadCount = liveMetrics?.process?.threads_count ?? 16;
  const procRssMb = liveMetrics?.process?.rss_mb ?? 184;
  const gcCounts = liveMetrics?.gc_stats?.counts ?? [12, 1, 0];
  const stateBackend = liveMetrics?.state_backend?.type ?? 'sqlite';

  const datapoints = metricsHistory?.datapoints || [];

  // Filtered audit log
  const filteredAuditLog = useMemo(() => {
    if (selectedPipelineFilter === 'all') return auditLog;
    return auditLog.filter((ev) => ev.job_id === selectedPipelineFilter);
  }, [auditLog, selectedPipelineFilter]);

  return (
    <div className="space-y-6 text-slate-100 pb-10">
      {/* Top Controls & Pipeline Filter Toolbar */}
      <div className="bg-slate-900/90 p-4 rounded-xl border border-slate-800 shadow-xl flex flex-col lg:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center shrink-0">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-bold text-slate-100">Deep Telemetry & Observability Center</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono font-medium">
                State Store: {stateBackend.toUpperCase()}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Workspace: <strong className="text-slate-200 font-mono">{projectId}</strong> • Real-time hardware utilization, MemoryGuard limits, and status matrix
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto justify-end">
          {/* Pipeline Selector Filter Dropdown */}
          <div className="flex items-center gap-1.5 bg-slate-950 px-2.5 py-1.5 rounded-lg border border-slate-800 text-xs">
            <Filter className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-slate-400 text-[11px] font-semibold">Scope:</span>
            <select
              value={selectedPipelineFilter}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedPipelineFilter(val);
                if (val !== 'all' && onSelectJob) {
                  onSelectJob(val);
                }
              }}
              className="bg-transparent text-slate-100 text-xs font-bold font-mono focus:outline-none cursor-pointer pr-1"
            >
              <option value="all" className="bg-slate-900 text-slate-100">
                All Pipelines ({pipelineList.length})
              </option>
              {pipelineList.map((p) => (
                <option key={p.id} value={p.id} className="bg-slate-900 text-slate-100">
                  {p.id} ({p.state || 'UNKNOWN'})
                </option>
              ))}
            </select>
          </div>

          {/* Timeframe selector buttons */}
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            {(['5m', '15m', '1h', '24h', 'custom'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2.5 py-1 rounded-md font-bold transition-all text-xs ${
                  timeframe === tf ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tf === 'custom' ? 'Custom' : tf}
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
            onClick={() => {
              onRefresh();
              fetchAllPipelineStatuses();
            }}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            title="Refresh All Metrics"
          >
            <RotateCw className={`w-3.5 h-3.5 ${loadingStatuses ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={() => setIsReportModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-bold shadow-md transition-all"
          >
            <FileText className="w-3.5 h-3.5" /> Export Report
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

        {/* Process Footprint & OS Threads */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-4 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-emerald-500" />
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">Process Footprint</span>
            <Server className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-100">{procRssMb} MB</div>
            <span className="text-xs text-slate-400">RSS Heap</span>
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

        {/* Stream Ingestion Rate & Scope Total */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-4 shadow-lg relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-amber-500" />
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
              {selectedPipelineFilter === 'all' ? 'Total Fleet Stream' : 'Pipeline Speed'}
            </span>
            <HardDrive className="w-4 h-4 text-amber-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-amber-400">
              {effectiveThroughput.toLocaleString()}
            </div>
            <span className="text-xs text-slate-400">rows / sec</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-4 space-y-1">
            <div className="flex justify-between">
              <span>{selectedPipelineFilter === 'all' ? 'Fleet Total Written:' : 'Rows Written:'}</span>
              <span className="text-emerald-400 font-mono font-bold">{totalAggregatedRows.toLocaleString()} rows</span>
            </div>
            <div className="flex justify-between">
              <span>Filtered Target:</span>
              <span className="text-indigo-300 font-mono font-bold truncate max-w-[120px]">
                {selectedPipelineFilter === 'all' ? 'All Pipelines' : selectedPipelineFilter}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* SECTION: Pipeline Fleet Status & Execution Matrix */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-bold text-slate-100">Pipeline Fleet Status & Performance Breakdown</h3>
            <span className="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-[10px] font-mono text-slate-300 font-bold">
              {pipelineList.length} Pipelines
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">REST Status Synchronizer</span>
            <button
              onClick={fetchAllPipelineStatuses}
              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold flex items-center gap-1 transition-colors"
            >
              <RotateCw className="w-3 h-3" /> Refresh Fleet
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse font-sans">
            <thead>
              <tr className="bg-slate-950 text-slate-300 font-semibold border-b border-slate-800">
                <th className="py-3 px-3">Pipeline ID & Tenant</th>
                <th className="py-3 px-3">State</th>
                <th className="py-3 px-3">Total Rows</th>
                <th className="py-3 px-3">Throughput</th>
                <th className="py-3 px-3">Duration</th>
                <th className="py-3 px-3">RAM</th>
                <th className="py-3 px-3">Health & Error Diagnostics</th>
                <th className="py-3 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
              {pipelineList.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-500 font-sans">
                    No pipelines found in workspace <strong>{projectId}</strong>.
                  </td>
                </tr>
              ) : (
                pipelineList.map((pipe) => {
                  const detail = pipelineDetails[pipe.id];
                  const state = detail?.state || pipe.state || 'UNKNOWN';
                  const metrics = detail?.metrics;
                  const isFailed = state === 'FAILED' || !!detail?.error;
                  const isFiltered = selectedPipelineFilter === pipe.id;

                  return (
                    <tr
                      key={pipe.id}
                      className={`transition-colors ${
                        isFiltered
                          ? 'bg-indigo-950/40 border-l-4 border-indigo-500'
                          : isFailed
                          ? 'bg-rose-950/20 hover:bg-rose-950/40'
                          : 'hover:bg-slate-800/40'
                      }`}
                    >
                      <td className="py-2.5 px-3">
                        <div className="font-bold text-indigo-400">{pipe.id}</div>
                        <div className="text-[10px] text-slate-500 font-sans">{projectId}</div>
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                            state === 'COMPLETED'
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                              : state === 'FAILED'
                              ? 'bg-rose-500/20 text-rose-300 border-rose-500/40 animate-pulse'
                              : state === 'PAUSED'
                              ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                              : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30'
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              state === 'COMPLETED'
                                ? 'bg-emerald-400'
                                : state === 'FAILED'
                                ? 'bg-rose-400'
                                : state === 'PAUSED'
                                ? 'bg-amber-400'
                                : 'bg-cyan-400'
                            }`}
                          />
                          {state}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-bold text-slate-200">
                        {metrics?.rows_processed !== undefined ? metrics.rows_processed.toLocaleString() : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-cyan-400">
                        {metrics?.rows_per_sec !== undefined ? `${metrics.rows_per_sec.toLocaleString()} r/s` : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400">
                        {metrics?.duration_sec !== undefined ? `${metrics.duration_sec}s` : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400">
                        {metrics?.memory_percent !== undefined ? `${metrics.memory_percent}%` : '—'}
                      </td>
                      <td className="py-2.5 px-3 max-w-xs font-sans text-xs">
                        {isFailed ? (
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-rose-300 font-mono text-[11px]" title={detail?.error?.message}>
                              {detail?.error?.message || 'Execution Failure'}
                            </span>
                            <button
                              onClick={() =>
                                setSelectedErrorModal({
                                  job_id: pipe.id,
                                  from_state: detail?.error?.failed_at_state || 'CHECKPOINTING',
                                  to_state: 'FAILED',
                                  error_message: detail?.error?.message || 'Pipeline Execution Failure',
                                  traceback: detail?.error?.traceback || detail?.error?.message,
                                  metadata: detail?.error,
                                  timestamp: metrics?.timestamp,
                                })
                              }
                              className="px-2 py-0.5 rounded bg-rose-800 hover:bg-rose-700 text-white font-bold text-[10px] shrink-0 flex items-center gap-1 shadow-sm transition-colors"
                            >
                              <Maximize2 className="w-3 h-3" /> View Trace
                            </button>
                          </div>
                        ) : (
                          <span className="text-emerald-400 flex items-center gap-1 font-semibold text-[11px]">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Healthy
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          onClick={() => {
                            if (isFiltered) {
                              setSelectedPipelineFilter('all');
                            } else {
                              setSelectedPipelineFilter(pipe.id);
                              if (onSelectJob) onSelectJob(pipe.id);
                            }
                          }}
                          className={`px-2.5 py-1 rounded text-[11px] font-bold transition-colors ${
                            isFiltered
                              ? 'bg-indigo-600 text-white'
                              : 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                          }`}
                        >
                          {isFiltered ? 'Showing' : 'Filter View'}
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Historical Throughput Chart & Metrics Stream */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-5 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-bold text-slate-100">Telemetry History & Throughput Trend</h3>
            <span className="text-[10px] text-slate-500 font-mono">10s Intervals</span>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-2">
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

      {/* Audit Trail & FSM Transition Log Table */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-5 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-slate-100">Audit Trail & FSM State Transition Log</h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
              {filteredAuditLog.length} Events {selectedPipelineFilter !== 'all' ? `(Filtered: ${selectedPipelineFilter})` : ''}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {selectedPipelineFilter !== 'all' && (
              <button
                onClick={() => setSelectedPipelineFilter('all')}
                className="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold underline"
              >
                Clear Filter (Show All)
              </button>
            )}
            <button
              onClick={onRefresh}
              className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
              title="Refresh Audit Log"
            >
              <RotateCw className="w-3.5 h-3.5" />
            </button>
          </div>
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
              {filteredAuditLog.length > 0 ? (
                filteredAuditLog.map((ev, idx) => {
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
                    No state transition events recorded for the selected scope.
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

      {/* Enhanced Executive Report Generation Modal */}
      {isReportModalOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl space-y-4 p-6 flex flex-col max-h-[90vh]">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <FileText className="w-5 h-5 text-indigo-400" /> Export Enterprise Fleet Health Report
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

                <div className="p-3.5 bg-slate-950 rounded-lg border border-slate-800 text-xs text-slate-400 space-y-1.5">
                  <div>• Target Workspace: <span className="text-slate-200 font-bold font-mono">{projectId}</span></div>
                  <div>• Timeframe Window: <span className="text-slate-200 font-bold">{timeframe}</span></div>
                  <div>• Scope: <span className="text-indigo-400 font-bold">{selectedPipelineFilter === 'all' ? `All Pipelines (${pipelineList.length})` : selectedPipelineFilter}</span></div>
                  <div>• Includes comprehensive per-pipeline throughput metrics, DLQ breakdown, and FSM audit trail.</div>
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
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow"
                  >
                    {generatingReport ? 'Compiling Report...' : 'Compile Executive Report'}
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4 flex-1 overflow-y-auto pr-1">
                <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-xs text-emerald-400 flex items-center gap-2 font-bold">
                  <CheckCircle2 className="w-4 h-4" /> Report compiled successfully ({generatedReport.generated_at})
                </div>

                <div className="p-4 bg-slate-950 border border-slate-800 rounded-lg font-mono text-xs text-slate-300 max-h-72 overflow-y-auto">
                  <pre>{JSON.stringify(generatedReport, null, 2)}</pre>
                </div>

                <div className="flex justify-end gap-2 border-t border-slate-800 pt-3">
                  <button
                    onClick={() => {
                      const blob = new Blob([JSON.stringify(generatedReport, null, 2)], { type: 'application/json' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `veloctra_fleet_report_${Date.now()}.json`;
                      a.click();
                    }}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow"
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

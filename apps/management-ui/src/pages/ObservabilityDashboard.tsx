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
  Clock,
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
    cpu_percent?: number;
    process_rss_mb?: number;
    process_cpu_percent?: number;
    is_completion_snapshot?: boolean;
    chunk_size?: number;
    duration_sec?: number;
    timestamp?: number;
    failure_policy?: any;
  };
  latest_checkpoint?: any;
  dlq_count?: number;
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

  // Pipeline Event Log State
  const [pipelineEvents, setPipelineEvents] = useState<any[]>([]);
  const [eventSeverityFilter, setEventSeverityFilter] = useState<string>('all');
  const [loadingEvents, setLoadingEvents] = useState(false);

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

  // Sync selectedPipelineFilter when prop changes
  useEffect(() => {
    if (selectedJobId && selectedJobId !== selectedPipelineFilter) {
      setSelectedPipelineFilter(selectedJobId);
    }
  }, [selectedJobId]);

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

  // Fetch structured pipeline events for selected pipeline
  const fetchPipelineEvents = async (jobId: string) => {
    try {
      setLoadingEvents(true);
      const sevParam = eventSeverityFilter !== 'all' ? `&severity=${eventSeverityFilter}` : '';
      const res = await fetch(`/pipelines/${jobId}/events?limit=100${sevParam}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setPipelineEvents(data.events || []);
      }
    } catch (err) {
      console.error('Failed to fetch pipeline events:', err);
    } finally {
      setLoadingEvents(false);
    }
  };

  useEffect(() => {
    if (selectedPipelineFilter && selectedPipelineFilter !== 'all') {
      fetchPipelineEvents(selectedPipelineFilter);
    } else {
      setPipelineEvents([]);
    }
  }, [selectedPipelineFilter, eventSeverityFilter]);

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
        data.pipeline_fleet = Object.values(pipelineDetails);
        setGeneratedReport(data);
      }
    } catch (err) {
      console.error('Report generation error:', err);
    } finally {
      setGeneratingReport(false);
    }
  };

  // Full pipelines fleet list
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

  // Filtered pipelines list strictly respecting the Scope dropdown
  const displayedPipelineList = useMemo(() => {
    if (selectedPipelineFilter === 'all') {
      return pipelineList;
    }
    return pipelineList.filter((p) => p.id === selectedPipelineFilter);
  }, [pipelineList, selectedPipelineFilter]);

  // Active single-pipeline detail when scoped
  const activeDetail = selectedPipelineFilter !== 'all' ? pipelineDetails[selectedPipelineFilter] : null;
  const isPipelineSelected = selectedPipelineFilter !== 'all' && activeDetail;
  const isSelectedFinished = isPipelineSelected && ['COMPLETED', 'FAILED', 'PAUSED'].includes(activeDetail?.state || '');

  // Computed Scope Metrics:
  const totalAggregatedRows = useMemo(() => {
    if (isPipelineSelected) {
      return activeDetail?.metrics?.rows_processed ?? 0;
    }
    return Object.values(pipelineDetails).reduce((sum, p) => sum + (p.metrics?.rows_processed || 0), 0) || (progress?.rows_processed ?? 0);
  }, [isPipelineSelected, activeDetail, pipelineDetails, progress]);

  const effectiveThroughput = useMemo(() => {
    if (isPipelineSelected) {
      return activeDetail?.metrics?.rows_per_sec ?? 0;
    }
    return Object.values(pipelineDetails).reduce((sum, p) => sum + (p.metrics?.rows_per_sec || 0), 0) || (progress?.rows_per_sec ?? 0);
  }, [isPipelineSelected, activeDetail, pipelineDetails, progress]);

  // CPU & RAM Metrics:
  const cpuPct = useMemo(() => {
    if (isPipelineSelected && isSelectedFinished && activeDetail?.metrics?.cpu_percent !== undefined) {
      return activeDetail.metrics.cpu_percent;
    }
    return liveMetrics?.system?.cpu_percent ?? 0;
  }, [isPipelineSelected, isSelectedFinished, activeDetail, liveMetrics]);

  const memoryPct = useMemo(() => {
    if (isPipelineSelected && isSelectedFinished && activeDetail?.metrics?.memory_percent !== undefined) {
      return activeDetail.metrics.memory_percent;
    }
    return liveMetrics?.system?.memory_percent ?? progress?.memory_percent ?? 70.0;
  }, [isPipelineSelected, isSelectedFinished, activeDetail, liveMetrics, progress]);

  const procRssMb = useMemo(() => {
    if (isPipelineSelected && isSelectedFinished && activeDetail?.metrics?.process_rss_mb !== undefined) {
      return activeDetail.metrics.process_rss_mb;
    }
    return liveMetrics?.process?.rss_mb ?? 184;
  }, [isPipelineSelected, isSelectedFinished, activeDetail, liveMetrics]);

  const cpuCores = liveMetrics?.system?.cpu_cores ?? 8;
  const memUsedGb = liveMetrics?.system?.memory_used_gb ?? (liveMetrics?.system?.memory_total_mb ? ((liveMetrics.system.memory_total_mb - liveMetrics.system.memory_available_mb) / 1024).toFixed(2) : '6.79');
  const memTotalGb = liveMetrics?.system?.memory_total_gb ?? (liveMetrics?.system?.memory_total_mb ? (liveMetrics.system.memory_total_mb / 1024).toFixed(2) : '8.00');
  const memAvailableGb = liveMetrics?.system?.memory_available_gb ?? (liveMetrics?.system?.memory_available_mb ? (liveMetrics.system.memory_available_mb / 1024).toFixed(2) : '1.21');
  const threadCount = liveMetrics?.process?.threads_count ?? 16;
  const gcCounts = liveMetrics?.gc_stats?.counts ?? [12, 1, 0];
  const stateBackend = liveMetrics?.state_backend?.type ?? 'sqlite';

  const datapoints = metricsHistory?.datapoints || [];

  // Filtered audit log
  const filteredAuditLog = useMemo(() => {
    if (selectedPipelineFilter === 'all') return auditLog;
    return auditLog.filter((ev) => ev.job_id === selectedPipelineFilter);
  }, [auditLog, selectedPipelineFilter]);

  return (
    <div className="space-y-6 text-slate-900 pb-10">
      {/* Top Controls & Pipeline Filter Toolbar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col lg:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-bold text-slate-900">Deep Telemetry & Observability Center</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 font-mono font-bold">
                State Store: {stateBackend.toUpperCase()}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Workspace: <strong className="text-slate-800 font-mono">{projectId}</strong> • Live hardware utilization, completion snapshots, and fleet metrics
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto justify-end">
          {/* Pipeline Selector Filter Dropdown */}
          <div className="flex items-center gap-1.5 bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200 text-xs">
            <Filter className="w-3.5 h-3.5 text-indigo-600" />
            <span className="text-slate-500 text-[11px] font-semibold">Scope:</span>
            <select
              value={selectedPipelineFilter}
              onChange={(e) => {
                const val = e.target.value;
                setSelectedPipelineFilter(val);
                if (val !== 'all' && onSelectJob) {
                  onSelectJob(val);
                }
              }}
              className="bg-transparent text-slate-900 text-xs font-bold font-mono focus:outline-none cursor-pointer pr-1"
            >
              <option value="all">All Pipelines ({pipelineList.length})</option>
              {pipelineList.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.id} ({p.state || 'UNKNOWN'})
                </option>
              ))}
            </select>
          </div>

          {/* Timeframe selector buttons */}
          <div className="flex items-center gap-1 bg-slate-50 p-1 rounded-lg border border-slate-200 text-xs">
            {(['5m', '15m', '1h', '24h', 'custom'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2.5 py-1 rounded-md font-bold transition-all text-xs ${
                  timeframe === tf ? 'bg-indigo-600 text-white shadow-2xs' : 'text-slate-600 hover:text-slate-900'
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
                className="px-2 py-1 bg-white border border-slate-200 rounded text-slate-800 text-[11px]"
              />
              <span className="text-slate-400">to</span>
              <input
                type="datetime-local"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
                className="px-2 py-1 bg-white border border-slate-200 rounded text-slate-800 text-[11px]"
              />
            </div>
          )}

          <button
            onClick={() => {
              onRefresh();
              fetchAllPipelineStatuses();
              if (selectedPipelineFilter !== 'all') fetchPipelineEvents(selectedPipelineFilter);
            }}
            className="p-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-slate-600 hover:text-slate-900 transition-colors shadow-2xs"
            title="Refresh All Metrics"
          >
            <RotateCw className={`w-3.5 h-3.5 ${loadingStatuses ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={() => setIsReportModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold shadow-sm transition-all"
          >
            <FileText className="w-3.5 h-3.5" /> Export Report
          </button>
        </div>
      </div>

      {/* 4 Deep Hardware & Execution Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* CPU Hardware Gauge */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm relative overflow-hidden">
          <div className={`absolute top-0 left-0 right-0 h-1 ${cpuPct > 75 ? 'bg-rose-500' : 'bg-indigo-600'}`} />
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-700">CPU Utilization</span>
            <Cpu className="w-4 h-4 text-indigo-600" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-900">{cpuPct}%</div>
            <span className="text-xs text-slate-500">({cpuCores} cores)</span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-1.5 mt-3 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${cpuPct > 75 ? 'bg-rose-500' : 'bg-indigo-600'}`}
              style={{ width: `${Math.min(cpuPct, 100)}%` }}
            />
          </div>
          <div className="text-[11px] text-slate-500 mt-2 flex justify-between items-center">
            <span>Limit: 75.0%</span>
            <span className={`font-semibold ${isSelectedFinished ? 'text-indigo-600' : cpuPct <= 75 ? 'text-emerald-600' : 'text-rose-600'}`}>
              {isSelectedFinished ? 'Snapshot at Completion' : cpuPct <= 75 ? '✓ Governed Live' : '⚠ Backpressure'}
            </span>
          </div>
        </div>

        {/* RAM Hardware Gauge */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm relative overflow-hidden">
          <div className={`absolute top-0 left-0 right-0 h-1 ${memoryPct > 80 ? 'bg-rose-500' : 'bg-purple-600'}`} />
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-700">RAM Allocation</span>
            <Activity className="w-4 h-4 text-purple-600" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-900">{memoryPct}%</div>
            <span className="text-xs text-slate-500">({memUsedGb} / {memTotalGb} GB)</span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-1.5 mt-3 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${memoryPct > 80 ? 'bg-rose-500' : 'bg-purple-600'}`}
              style={{ width: `${Math.min(memoryPct, 100)}%` }}
            />
          </div>
          <div className="text-[11px] text-slate-500 mt-2 flex justify-between items-center">
            <span>Avail: {memAvailableGb} GB</span>
            <span className={`font-semibold ${isSelectedFinished ? 'text-purple-600' : memoryPct <= 80 ? 'text-emerald-600' : 'text-rose-600'}`}>
              {isSelectedFinished ? 'Snapshot at Completion' : memoryPct <= 80 ? '✓ MemoryGuard Normal' : '⚠ Guard Activated'}
            </span>
          </div>
        </div>

        {/* Process Footprint & OS Threads */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-emerald-500" />
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-700">Application Footprint</span>
            <Server className="w-4 h-4 text-emerald-600" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-slate-900">{procRssMb} MB</div>
            <span className="text-xs text-slate-500">Veloctra RSS Heap</span>
          </div>
          <div className="text-[11px] text-slate-500 mt-3 space-y-1">
            <div className="flex justify-between">
              <span>Active OS Threads:</span>
              <span className="text-slate-800 font-mono font-bold">{threadCount}</span>
            </div>
            <div className="flex justify-between">
              <span>GC Cycles (0/1/2):</span>
              <span className="text-slate-800 font-mono">{gcCounts.join('/')}</span>
            </div>
          </div>
        </div>

        {/* Stream Ingestion Rate & Scope Total */}
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-1 bg-amber-500" />
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
              {selectedPipelineFilter === 'all' ? 'Fleet Throughput' : 'Pipeline Speed'}
            </span>
            <HardDrive className="w-4 h-4 text-amber-500" />
          </div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold font-mono text-amber-600">
              {effectiveThroughput.toLocaleString()}
            </div>
            <span className="text-xs text-slate-500">rows / sec</span>
          </div>
          <div className="text-[11px] text-slate-500 mt-3 space-y-1">
            <div className="flex justify-between">
              <span>{selectedPipelineFilter === 'all' ? 'Fleet Total Written:' : 'Rows Written:'}</span>
              <span className="text-emerald-600 font-mono font-bold">{totalAggregatedRows.toLocaleString()} rows</span>
            </div>
            <div className="flex justify-between">
              <span>Scope:</span>
              <span className="text-indigo-600 font-mono font-bold truncate max-w-[130px]">
                {selectedPipelineFilter === 'all' ? 'All Pipelines' : selectedPipelineFilter}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* SECTION: Pipeline Fleet Status & Execution Matrix */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-600" />
            <h3 className="text-sm font-bold text-slate-900">
              {selectedPipelineFilter === 'all'
                ? 'Pipeline Fleet Status & Performance Breakdown'
                : `Pipeline Status & Performance Breakdown — ${selectedPipelineFilter}`}
            </h3>
            <span className="px-2 py-0.5 rounded-full bg-slate-100 border border-slate-200 text-[10px] font-mono text-slate-700 font-bold">
              {selectedPipelineFilter === 'all'
                ? `${pipelineList.length} Pipelines`
                : `Scope: ${selectedPipelineFilter} (1 of ${pipelineList.length})`}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {selectedPipelineFilter !== 'all' && (
              <button
                onClick={() => {
                  setSelectedPipelineFilter('all');
                  if (onSelectJob) onSelectJob('');
                }}
                className="px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-700 text-xs font-bold flex items-center gap-1 transition-colors"
                title="Clear filter and view all fleet pipelines"
              >
                Show All Pipelines ({pipelineList.length})
              </button>
            )}
            <button
              onClick={fetchAllPipelineStatuses}
              className="px-2.5 py-1 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-bold flex items-center gap-1 transition-colors"
            >
              <RotateCw className="w-3 h-3" /> Refresh Fleet
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse font-sans">
            <thead>
              <tr className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                <th className="py-3 px-3">Pipeline ID</th>
                <th className="py-3 px-3">State</th>
                <th className="py-3 px-3">Total Rows</th>
                <th className="py-3 px-3">Throughput</th>
                <th className="py-3 px-3">Duration</th>
                <th className="py-3 px-3">RAM</th>
                <th className="py-3 px-3">Health & Error Diagnostics</th>
                <th className="py-3 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono text-slate-700">
              {displayedPipelineList.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-400 font-sans">
                    {selectedPipelineFilter === 'all'
                      ? `No pipelines found in workspace ${projectId}.`
                      : `No pipeline found matching scope '${selectedPipelineFilter}'.`}
                  </td>
                </tr>
              ) : (
                displayedPipelineList.map((pipe) => {
                  const detail = pipelineDetails[pipe.id];
                  const state = detail?.state || pipe.state || 'UNKNOWN';
                  const metrics = detail?.metrics;
                  const isFailed = state === 'FAILED';
                  const isFiltered = selectedPipelineFilter === pipe.id;
                  const dlqCount = detail?.dlq_count || 0;

                  return (
                    <tr
                      key={pipe.id}
                      className={`transition-colors ${
                        isFiltered
                          ? 'bg-indigo-50/70 border-l-4 border-indigo-600'
                          : isFailed
                          ? 'bg-rose-50/40 hover:bg-rose-50/70'
                          : 'hover:bg-slate-50'
                      }`}
                    >
                      <td className="py-2.5 px-3">
                        <div className="font-bold text-indigo-700">{pipe.id}</div>
                        <div className="text-[10px] text-slate-400 font-sans">{projectId}</div>
                      </td>
                      <td className="py-2.5 px-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                            state === 'COMPLETED'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : state === 'FAILED'
                              ? 'bg-rose-50 text-rose-700 border-rose-200 animate-pulse'
                              : state === 'PAUSED'
                              ? 'bg-amber-50 text-amber-700 border-amber-200'
                              : 'bg-cyan-50 text-cyan-700 border-cyan-200'
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              state === 'COMPLETED'
                                ? 'bg-emerald-500'
                                : state === 'FAILED'
                                ? 'bg-rose-500'
                                : state === 'PAUSED'
                                ? 'bg-amber-500'
                                : 'bg-cyan-500'
                            }`}
                          />
                          {state}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-bold text-slate-900">
                        {metrics?.rows_processed !== undefined ? metrics.rows_processed.toLocaleString() : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-cyan-700 font-bold">
                        {metrics?.rows_per_sec !== undefined ? `${metrics.rows_per_sec.toLocaleString()} r/s` : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-slate-500">
                        {metrics?.duration_sec !== undefined ? `${metrics.duration_sec}s` : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-slate-500">
                        {metrics?.memory_percent !== undefined ? `${metrics.memory_percent}%` : '—'}
                      </td>
                      <td className="py-2.5 px-3 max-w-xs font-sans text-xs">
                        {isFailed ? (
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-rose-700 font-mono text-[11px]" title={detail?.error?.message}>
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
                              className="px-2 py-0.5 rounded bg-rose-600 hover:bg-rose-700 text-white font-bold text-[10px] shrink-0 flex items-center gap-1 shadow-2xs transition-colors"
                            >
                              <Maximize2 className="w-3 h-3" /> View Trace
                            </button>
                          </div>
                        ) : state === 'COMPLETED' ? (
                          <div className="flex items-center gap-2">
                            <span className="text-emerald-700 flex items-center gap-1 font-semibold text-[11px]">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Completed Clean
                            </span>
                            {dlqCount > 0 && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 font-mono font-bold" title="DLQ records isolated without failing pipeline">
                                {dlqCount} in DLQ
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-500 text-[11px]">{state}</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <button
                          onClick={() => {
                            if (isFiltered) {
                              setSelectedPipelineFilter('all');
                              if (onSelectJob) onSelectJob('');
                            } else {
                              setSelectedPipelineFilter(pipe.id);
                              if (onSelectJob) onSelectJob(pipe.id);
                            }
                          }}
                          className={`px-2.5 py-1 rounded text-[11px] font-bold transition-colors shadow-2xs ${
                            isFiltered
                              ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                              : 'bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200'
                          }`}
                        >
                          {isFiltered ? 'Show All Fleet' : 'Scope Pipeline'}
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
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-600" />
            <h3 className="text-sm font-bold text-slate-900">Telemetry History & Throughput Trend</h3>
            <span className="text-[10px] text-slate-400 font-mono">10s Intervals</span>
          </div>
          <div className="text-xs text-slate-500 flex items-center gap-2">
            {loadingMetrics && <span className="text-indigo-600 animate-pulse font-mono font-semibold">Syncing trend...</span>}
          </div>
        </div>

        {datapoints.length > 0 ? (
          <div className="h-48 flex items-end gap-1.5 pt-6 pb-2 px-2 bg-slate-50 rounded-lg border border-slate-200 overflow-x-auto">
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
                    className="w-full bg-gradient-to-t from-indigo-500 to-cyan-400 rounded-t-sm hover:brightness-110 transition-all cursor-pointer"
                  />
                  {/* Tooltip on hover */}
                  <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute bottom-full mb-2 bg-slate-900 border border-slate-800 text-[10px] text-white p-2 rounded-lg shadow-2xl z-20 pointer-events-none whitespace-nowrap">
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
          <div className="h-48 flex items-center justify-center bg-slate-50 rounded-lg border border-slate-200 text-slate-400 text-xs font-mono">
            No historical data points in the selected window. Run a pipeline to stream telemetry metrics.
          </div>
        )}
      </div>

      {/* SECTION: Pipeline Structured Event Log (When a pipeline is selected) */}
      {selectedPipelineFilter !== 'all' && (
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-indigo-600" />
              <h3 className="text-sm font-bold text-slate-900">Structured Pipeline Event Log</h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 font-bold">
                Run ID: {selectedPipelineFilter}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Severity:</span>
              <select
                value={eventSeverityFilter}
                onChange={(e) => setEventSeverityFilter(e.target.value)}
                className="bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold px-2 py-1 rounded-lg focus:outline-none"
              >
                <option value="all">All Severities</option>
                <option value="INFO">INFO</option>
                <option value="WARN">WARN</option>
                <option value="ERROR">ERROR</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
              <button
                onClick={() => fetchPipelineEvents(selectedPipelineFilter)}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600"
                title="Refresh Events"
              >
                <RotateCw className={`w-3.5 h-3.5 ${loadingEvents ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
            {pipelineEvents.length === 0 ? (
              <div className="p-6 text-center text-slate-400 text-xs">
                No events recorded for this pipeline with current filters.
              </div>
            ) : (
              pipelineEvents.map((ev: any, idx: number) => {
                const sev = ev.severity || 'INFO';
                const isErr = sev === 'ERROR' || sev === 'CRITICAL';
                const isWarn = sev === 'WARN';
                return (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg border text-xs transition-all ${
                      isErr
                        ? 'bg-rose-50 border-rose-200 text-rose-900'
                        : isWarn
                        ? 'bg-amber-50 border-amber-200 text-amber-900'
                        : 'bg-slate-50 border-slate-200 text-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold font-mono uppercase ${
                            isErr
                              ? 'bg-rose-600 text-white'
                              : isWarn
                              ? 'bg-amber-600 text-white'
                              : 'bg-indigo-100 text-indigo-800'
                          }`}
                        >
                          {sev}
                        </span>
                        <span className="font-mono font-bold text-slate-900">{ev.event_type}</span>
                        {ev.chunk_index !== undefined && ev.chunk_index !== null && (
                          <span className="text-[10px] text-slate-500 font-mono">(Chunk {ev.chunk_index})</span>
                        )}
                      </div>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {typeof ev.created_at === 'number' ? new Date(ev.created_at * 1000).toLocaleTimeString() : ev.created_at}
                      </span>
                    </div>
                    {ev.message && <p className="mt-1 text-xs text-slate-700 font-mono break-all">{ev.message}</p>}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Audit Trail & FSM Transition Log Table */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <ClipboardList className="w-4 h-4 text-indigo-600" />
            <h3 className="text-sm font-bold text-slate-900">Audit Trail & FSM State Transition Log</h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-semibold">
              {filteredAuditLog.length} Events {selectedPipelineFilter !== 'all' ? `(Filtered: ${selectedPipelineFilter})` : ''}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {selectedPipelineFilter !== 'all' && (
              <button
                onClick={() => setSelectedPipelineFilter('all')}
                className="text-[11px] text-indigo-600 hover:text-indigo-800 font-semibold underline"
              >
                Clear Filter (Show All)
              </button>
            )}
            <button
              onClick={onRefresh}
              className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 transition-colors shadow-2xs"
              title="Refresh Audit Log"
            >
              <RotateCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse font-sans">
            <thead>
              <tr className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                <th className="py-2.5 px-3">State Transition</th>
                <th className="py-2.5 px-3">Workspace Tenant</th>
                <th className="py-2.5 px-3">Job Run ID</th>
                <th className="py-2.5 px-3">Metadata Context / Diagnostic Reason</th>
                <th className="py-2.5 px-3">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono text-slate-700">
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
                          ? 'bg-rose-50/70 hover:bg-rose-100/70 border-l-4 border-rose-500 text-rose-900'
                          : 'hover:bg-slate-50'
                      }`}
                    >
                      <td className="py-2.5 px-3 flex items-center gap-1.5 font-bold">
                        <span className="text-slate-500">{ev.from_state}</span>
                        <span className="text-indigo-600">→</span>
                        {ev.to_state === 'FAILED' ? (
                          <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-700 font-bold border border-rose-200 text-[11px] flex items-center gap-1">
                            <AlertCircle className="w-3 h-3 text-rose-600" /> FAILED
                          </span>
                        ) : (
                          <span className="text-emerald-700 font-bold">{ev.to_state}</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-slate-600">{ev.tenant_id}</td>
                      <td className="py-2.5 px-3 text-indigo-700 font-bold">{ev.job_id}</td>
                      <td className="py-2.5 px-3 max-w-sm">
                        {isFailed ? (
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-rose-800 font-sans font-medium text-xs">
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
                              className="px-2.5 py-1 rounded bg-rose-600 hover:bg-rose-700 text-white font-bold text-[10px] shrink-0 flex items-center gap-1 shadow-2xs transition-colors"
                            >
                              <Maximize2 className="w-3 h-3" /> Inspect Trace
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-500 truncate block text-[11px]">
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
                  <td colSpan={5} className="py-6 text-center text-slate-400 font-sans">
                    No state transition events recorded for the selected scope.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Audit Failure Inspection Modal (Light Mode, Wrapped & No Horizontal Scroll) */}
      {selectedErrorModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl space-y-4 p-6 text-slate-900 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-bold text-rose-700 flex items-center gap-2">
                <AlertOctagon className="w-5 h-5 text-rose-600" /> State Transition Failure Root Cause — {selectedErrorModal.job_id}
              </h3>
              <button
                onClick={() => setSelectedErrorModal(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md hover:bg-slate-100 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3.5 flex-1 overflow-y-auto overflow-x-hidden pr-1">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <div className="text-slate-500 font-bold uppercase text-[10px]">Transition</div>
                  <div className="text-rose-800 font-mono font-bold mt-1 break-all">
                    {selectedErrorModal.from_state} → {selectedErrorModal.to_state}
                  </div>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <div className="text-slate-500 font-bold uppercase text-[10px]">Job Run ID</div>
                  <div className="text-indigo-800 font-mono font-bold mt-1 truncate">{selectedErrorModal.job_id}</div>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 col-span-2 sm:col-span-1">
                  <div className="text-slate-500 font-bold uppercase text-[10px]">Timestamp</div>
                  <div className="text-slate-700 font-mono font-bold mt-1">
                    {typeof selectedErrorModal.timestamp === 'number'
                      ? new Date(selectedErrorModal.timestamp * 1000).toLocaleTimeString()
                      : selectedErrorModal.timestamp}
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Error Message</label>
                <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-lg text-rose-950 text-xs font-mono break-words break-all leading-relaxed whitespace-pre-wrap overflow-x-hidden">
                  {selectedErrorModal.error_message}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                    <Terminal className="w-3.5 h-3.5 text-slate-500" /> Complete Traceback & Execution Context
                  </label>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(selectedErrorModal.traceback || selectedErrorModal.error_message);
                      setCopiedAuditError(true);
                      setTimeout(() => setCopiedAuditError(false), 2000);
                    }}
                    className="text-xs text-indigo-700 hover:text-indigo-900 font-semibold flex items-center gap-1 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200 transition-colors"
                  >
                    {copiedAuditError ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                    {copiedAuditError ? 'Copied' : 'Copy Trace'}
                  </button>
                </div>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg font-mono text-xs text-slate-800 max-h-72 overflow-y-auto overflow-x-hidden whitespace-pre-wrap break-words break-all leading-relaxed select-text shadow-inner">
                  {selectedErrorModal.traceback || selectedErrorModal.error_message}
                </div>
              </div>

              {selectedErrorModal.metadata && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Full Transition Metadata JSON</label>
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg font-mono text-[11px] text-slate-700 max-h-36 overflow-y-auto overflow-x-hidden whitespace-pre-wrap break-words break-all">
                    <pre className="whitespace-pre-wrap break-words break-all">{JSON.stringify(selectedErrorModal.metadata, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
              <button
                onClick={() => setSelectedErrorModal(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Enhanced Executive Report Generation Modal (Light Mode) */}
      {isReportModalOpen && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl space-y-4 p-6 flex flex-col max-h-[90vh] text-slate-900">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <FileText className="w-5 h-5 text-indigo-600" /> Export Enterprise Fleet Health Report
              </h3>
              <button
                onClick={() => {
                  setIsReportModalOpen(false);
                  setGeneratedReport(null);
                }}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {!generatedReport ? (
              <form onSubmit={handleGenerateReport} className="space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Report Title</label>
                  <input
                    type="text"
                    value={reportTitle}
                    onChange={(e) => setReportTitle(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-900 text-xs focus:outline-none focus:border-indigo-600 focus:bg-white"
                  />
                </div>

                <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-600 space-y-1.5">
                  <div>• Target Workspace: <span className="text-slate-900 font-bold font-mono">{projectId}</span></div>
                  <div>• Timeframe Window: <span className="text-slate-900 font-bold">{timeframe}</span></div>
                  <div>• Scope: <span className="text-indigo-700 font-bold">{selectedPipelineFilter === 'all' ? `All Pipelines (${pipelineList.length})` : selectedPipelineFilter}</span></div>
                  <div>• Includes comprehensive per-pipeline throughput metrics, DLQ breakdown, and FSM audit trail.</div>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsReportModalOpen(false)}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={generatingReport}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow"
                  >
                    {generatingReport ? 'Compiling Report...' : 'Compile Executive Report'}
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4 flex-1 overflow-y-auto pr-1">
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-center gap-2 font-bold">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" /> Report compiled successfully ({generatedReport.generated_at})
                </div>

                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg font-mono text-xs text-slate-800 max-h-72 overflow-y-auto">
                  <pre>{JSON.stringify(generatedReport, null, 2)}</pre>
                </div>

                <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
                  <button
                    onClick={() => {
                      const blob = new Blob([JSON.stringify(generatedReport, null, 2)], { type: 'application/json' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = `veloctra_fleet_report_${Date.now()}.json`;
                      a.click();
                    }}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow"
                  >
                    <Download className="w-3.5 h-3.5" /> Download JSON
                  </button>
                  <button
                    onClick={() => {
                      setIsReportModalOpen(false);
                      setGeneratedReport(null);
                    }}
                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold"
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

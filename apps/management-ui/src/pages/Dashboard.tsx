import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Zap,
  Play,
  Pause,
  LogOut,
  RefreshCw,
  FolderGit2,
  Search,
  Activity,
  Layers,
  Sparkles,
  Gauge,
  Sliders,
  FileCode,
  LayoutDashboard,
  Network,
  UploadCloud,
  Shield,
  Plug,
  BookOpen,
  AlertTriangle,
  AlertOctagon,
  AlertCircle,
  Copy,
  Check,
  ExternalLink,
  Maximize2,
  ChevronDown,
  ChevronUp,
  Terminal,
  X,
  Clock,
  CheckCircle2,
} from 'lucide-react';

const formatJobTime = (ts?: number) => {
  if (!ts) return 'Active Run';
  const d = new Date(ts * 1000);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  if (isToday) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};
import { CircuitBreakerInfo, DLQRecord, FSMState, JobInfo, PipelineProgressEvent, PipelineErrorInfo } from '../types';
import { useTelemetryWebSocket } from '../hooks/useTelemetryWebSocket';
import { MetricCards } from '../components/MetricCards';
import { FSMPipelineVisualizer } from '../components/FSMPipelineVisualizer';
import { DLQInspector } from '../components/DLQInspector';
import { CircuitBreakerMonitor } from '../components/CircuitBreakerMonitor';
import { ProjectCreateModal } from '../components/ProjectCreateModal';
import { MultiTableConsolidator } from '../components/MultiTableConsolidator';
import { DataModelMapper } from '../components/DataModelMapper';
import { VisualDataModeler } from '../components/VisualDataModeler';
import { StudioWizardStep1 } from '../components/StudioWizardStep1';
import { BulkConfigUploader } from '../components/BulkConfigUploader';
import { ConfigEditor } from '../components/ConfigEditor';
import { ConnectionsManager } from './ConnectionsManager';
import { ObservabilityDashboard } from './ObservabilityDashboard';
import { SettingsRBAC } from './SettingsRBAC';
import { PlatformDocs } from './PlatformDocs';

interface DashboardProps {
  token: string;
  onLogout: () => void;
  initialNav?: 'dashboard' | 'observability' | 'dlq' | 'connections' | 'studio' | 'bulk' | 'settings' | 'docs';
}

export const Dashboard: React.FC<DashboardProps> = ({ token, onLogout, initialNav = 'dashboard' }) => {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<any[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [selectedWorkspace, setSelectedWorkspace] = useState('');
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);

  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  
  const [availablePipelines, setAvailablePipelines] = useState<string[]>([]);
  const [selectedLaunchPipeline, setSelectedLaunchPipeline] = useState('');
  const [connections, setConnections] = useState<any[]>([]);
  const [studioPipelineId, setStudioPipelineId] = useState<string>('new_pipeline_1');

  // Primary Navigation State linked with Router
  const [activeNav, setActiveNav] = useState<'dashboard' | 'observability' | 'dlq' | 'connections' | 'studio' | 'bulk' | 'settings' | 'docs'>(initialNav);

  useEffect(() => {
    setActiveNav(initialNav);
  }, [initialNav]);

  const handleNavClick = (nav: 'dashboard' | 'observability' | 'dlq' | 'connections' | 'studio' | 'bulk' | 'settings' | 'docs') => {
    setActiveNav(nav);
    if (nav === 'dashboard') navigate('/dashboard');
    else if (nav === 'observability') navigate('/observability');
    else if (nav === 'dlq') navigate('/dlq');
    else if (nav === 'connections') navigate('/connections');
    else if (nav === 'studio') navigate('/studio');
    else if (nav === 'bulk') navigate('/bulk-import');
    else if (nav === 'settings') navigate('/settings');
    else if (nav === 'docs') navigate('/docs');
  };

  // Sub-tabs inside Pipeline Studio
  const [searchParams, setSearchParams] = useSearchParams();
  const studioSubTab = (searchParams.get('subtab') as 'wizard_step1' | 'visual_modeler' | 'consolidate' | 'mapper' | 'yaml') || 'wizard_step1';
  
  const [wizardConfig, setWizardConfig] = useState<any>(null);

  const [currentState, setCurrentState] = useState<FSMState | null>(null);
  const [_configYaml, setConfigYaml] = useState('');

  const fetchCurrentConfig = async (pid: string) => {
    if (!pid || !token) return;
    try {
      const res = await fetch(`/configs/${encodeURIComponent(pid)}?tenant_id=${encodeURIComponent(selectedWorkspace || '')}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setConfigYaml(JSON.stringify(data, null, 2));

        const sources = data.sources || (data.source ? [data.source] : []);
        const mappedSources = sources.map((s: any) => {
          const sName = (s.name || '').toLowerCase().replace(/[\s-]/g, '_');
          const found = connections.find(c => c.id === sName || c.name === s.name || c.id === s.name);
          return { connection_id: found ? found.id : (sName || connections[0]?.id || '') };
        });

        const dests = data.destinations || [];
        const mappedDests = dests.map((d: any) => {
          const dName = (d.name || '').toLowerCase().replace(/[\s-]/g, '_');
          const found = connections.find(c => c.id === dName || c.name === d.name || c.id === d.name);
          return { connection_id: found ? found.id : (dName || connections[0]?.id || '') };
        });

        if (sources.length > 0) {
          const s = sources[0];
          const srcConn = s.connection_string || s.path || s.url || s.name || '';
          if (srcConn) {
            setSchemaConnectionString(srcConn);
          }
        }

        setWizardConfig({
          pipelineId: pid,
          primarySources: mappedSources.length > 0 ? mappedSources : [{ connection_id: '' }],
          secondarySources: [],
          destinations: mappedDests.length > 0 ? mappedDests : [{ connection_id: '' }]
        });
      }
    } catch (e) {
      console.error("Failed to fetch current config", e);
    }
  };

  const setStudioSubTab = (tab: string) => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('subtab', tab);
    setSearchParams(newParams, { replace: true });
    if (tab === 'yaml') {
      fetchCurrentConfig(studioPipelineId || selectedWorkspace);
    }
  };
  const [circuitBreakers, setCircuitBreakers] = useState<CircuitBreakerInfo[]>([]);
  const [dlqRecords, setDlqRecords] = useState<DLQRecord[]>([]);
  const [auditLog, setAuditLog] = useState<any[]>([]);

  // --- Shared Pipeline Studio Schema State ---
  const [schemaTables, setSchemaTables] = useState<any[]>([]);
  const [fieldMappings, setFieldMappings] = useState<Record<string, string>>({});
  const [mappingTypes, setMappingTypes] = useState<Record<string, 'direct' | 'function'>>({});
  const [encryptedFields, setEncryptedFields] = useState<Record<string, boolean>>({});
  const [schemaConnectionString, setSchemaConnectionString] = useState('raw_claims_zip_file');
  const [schemaLoading, setSchemaLoading] = useState(false);

  // --- Pipeline Import Modal State ---
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [importYamlText, setImportYamlText] = useState('');
  const [importPipelineId, setImportPipelineId] = useState('');
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      setImportYamlText(text);
      try {
        const parsed = JSON.parse(text);
        if (parsed.pipeline_id) setImportPipelineId(parsed.pipeline_id);
      } catch {
        const match = text.match(/pipeline_id:\s*([^\s\n]+)/);
        if (match && match[1]) setImportPipelineId(match[1].trim());
      }
    };
    reader.readAsText(file);
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importYamlText.trim()) return;
    setImporting(true);
    setImportStatus(null);

    let pid = importPipelineId.trim();
    if (!pid) {
      const match = importYamlText.match(/pipeline_id:\s*([^\s\n]+)/);
      if (match && match[1]) pid = match[1].trim();
      else pid = `imported_pipeline_${Date.now()}`;
    }

    try {
      const res = await fetch(`/configs/${encodeURIComponent(pid)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          yaml_content: importYamlText,
          tenant_id: selectedWorkspace
        })
      });
      if (res.ok) {
        setImportStatus(`Pipeline '${pid}' imported and registered successfully!`);
        fetchPipelines();
        setStudioPipelineId(pid);
        setTimeout(() => {
          setIsImportModalOpen(false);
          setImportStatus(null);
          setImportYamlText('');
          setImportPipelineId('');
        }, 1200);
      } else {
        const err = await res.json();
        setImportStatus(`Import Error: ${err.detail || 'Failed to save configuration'}`);
      }
    } catch (err: any) {
      setImportStatus(`Import Error: ${err.message}`);
    } finally {
      setImporting(false);
    }
  };

  const fetchSchema = async (customConn?: string) => {
    setSchemaLoading(true);
    const targetConn = customConn || schemaConnectionString || (
      wizardConfig?.primarySources?.[0]?.connection_id
        ? (connections.find(c => c.id === wizardConfig.primarySources[0].connection_id)?.url || wizardConfig.primarySources[0].connection_id)
        : (connections[0]?.url || 'raw_claims_zip_file')
    );
    try {
      const res = await fetch('/configs/schema-discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ connection_string: targetConn }),
      });
      if (res.ok) {
        const data = await res.json();
        const tables = data.tables || [];
        setSchemaTables(tables);
        
        // Auto-initialize mappings
        if (tables.length > 0) {
          const initialMap: Record<string, string> = {};
          const initialTypes: Record<string, 'direct' | 'function'> = {};
          const initialEnc: Record<string, boolean> = {};
          
          tables.forEach((tbl: any) => {
            (tbl.columns || []).forEach((c: string) => {
              const key = `${tbl.table_name}.${c}`;
              initialMap[key] = c;
              initialTypes[key] = 'direct';
              initialEnc[key] = c.toLowerCase().includes('ssn') || c.toLowerCase().includes('card') || c.toLowerCase().includes('birth') || c.toLowerCase().includes('death');
            });
          });
          setFieldMappings(initialMap);
          setMappingTypes(initialTypes);
          setEncryptedFields(initialEnc);
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSchemaLoading(false);
    }
  };

  const { isConnected, progress, lastTransition } = useTelemetryWebSocket(
    selectedJobId,
    token
  );
  const [jobMetrics, setJobMetrics] = useState<PipelineProgressEvent | null>(null);
  const [jobError, setJobError] = useState<PipelineErrorInfo | null>(null);
  const [isErrorModalOpen, setIsErrorModalOpen] = useState(false);
  const [isErrorExpanded, setIsErrorExpanded] = useState(false);
  const [copiedError, setCopiedError] = useState(false);

  const fetchProjects = async () => {
    try {
      setProjectsLoading(true);
      const res = await fetch('/projects', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) {
        onLogout();
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const fetchedProjects = data.projects || [];
        setProjects(fetchedProjects);
        if (fetchedProjects.length === 0) {
          setIsProjectModalOpen(true);
        } else if (!selectedWorkspace || !fetchedProjects.some((p: any) => p.id === selectedWorkspace)) {
          setSelectedWorkspace(fetchedProjects[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch projects:', err);
    } finally {
      setProjectsLoading(false);
    }
  };

  const fetchPipelines = async () => {
    if (!selectedWorkspace) return;
    try {
      const res = await fetch(`/configs/list?tenant_id=${encodeURIComponent(selectedWorkspace)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const pipeList = data.pipelines || [];
        setAvailablePipelines(pipeList);
        if (pipeList.length > 0) {
          setSelectedLaunchPipeline(pipeList[0]);
          const currentId = studioPipelineId && pipeList.includes(studioPipelineId) ? studioPipelineId : pipeList[0];
          setStudioPipelineId(currentId);
          fetchCurrentConfig(currentId);
        }
      }
    } catch (err) {
      console.error('Failed to fetch pipelines:', err);
    }
  };

  const fetchConnections = async () => {
    if (!selectedWorkspace) return;
    try {
      const res = await fetch(`/configs/connections/list?tenant_id=${encodeURIComponent(selectedWorkspace)}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setConnections(data.connections || []);
      }
    } catch (err) {
      console.error('Failed to fetch connections:', err);
    }
  };

  const fetchJobs = async (workspaceId?: string) => {
    const ws = workspaceId || selectedWorkspace;
    if (!ws) return;
    try {
      const res = await fetch(`/pipelines?project_id=${encodeURIComponent(ws)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) {
        onLogout();
        return;
      }
      const data = await res.json();
      const rawList: JobInfo[] = data.job_list || Object.entries(data.jobs || {}).map(([id, state]) => ({
        id,
        state: state as FSMState,
      }));
      const sortedJobs = [...rawList].sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
      setJobs(sortedJobs);
      if (sortedJobs.length > 0) {
        const targetId = (!selectedJobId || !sortedJobs.some(j => j.id === selectedJobId)) ? sortedJobs[0].id : selectedJobId;
        setSelectedJobId(targetId);
        fetchJobDetails(targetId);
      } else {
        setSelectedJobId(null);
      }
    } catch (err) {
      console.error('Failed to fetch jobs:', err);
    }
  };

  const fetchJobDetails = async (jobId: string) => {
    try {
      const statusRes = await fetch(`/pipelines/${jobId}/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (statusRes.ok) {
        const data = await statusRes.json();
        setCurrentState(data.state as FSMState);
        setCircuitBreakers(Object.values(data.circuit_breakers || {}));
        if (data.metrics) {
          setJobMetrics({
            event: 'pipeline_progress',
            job_id: jobId,
            rows_processed: data.metrics.rows_processed || 0,
            chunks_processed: data.metrics.chunks_processed || 0,
            rows_per_sec: data.metrics.rows_per_sec || 0,
            memory_percent: data.metrics.memory_percent || 0,
            chunk_size: data.metrics.chunk_size || 0,
            timestamp: data.metrics.timestamp || Date.now(),
          });
        }
        setJobError(data.error || (data.state === 'FAILED' ? { message: 'Pipeline run terminated with a runtime failure.' } : null));
      }

      const dlqRes = await fetch(`/pipelines/${jobId}/dlq?include_replayed=true&limit=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (dlqRes.ok) {
        const data = await dlqRes.json();
        setDlqRecords(data.records || []);
      }

      const auditRes = await fetch(`/pipelines/${jobId}/audit?limit=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (auditRes.ok) {
        const data = await auditRes.json();
        setAuditLog(data.events || []);
      }

      const configRes = await fetch(`/configs/${selectedWorkspace}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (configRes.ok) {
        const data = await configRes.json();
        setConfigYaml(JSON.stringify(data, null, 2));
      }
    } catch (err) {
      console.error('Error fetching job details:', err);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  useEffect(() => {
    if (selectedWorkspace) {
      fetchPipelines();
      fetchConnections();
      fetchJobs(selectedWorkspace);
    }
  }, [selectedWorkspace]);

  useEffect(() => {
    if (selectedJobId) {
      fetchJobDetails(selectedJobId);
    }
  }, [selectedJobId]);

  useEffect(() => {
    if (lastTransition) {
      setCurrentState(lastTransition.state);
    }
  }, [lastTransition]);

  const handleStartJob = async () => {
    if (!selectedLaunchPipeline) return;
    try {
      const res = await fetch(`/pipelines/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ pipeline_id: selectedLaunchPipeline }),
      });
      if (res.ok) {
        const data = await res.json();
        await fetchJobs(selectedWorkspace);
        setSelectedJobId(data.job_id);
      }
    } catch (err) {
      console.error('Failed to start job:', err);
    }
  };



  const handleStopJob = async (stopMode: 'rollback' | 'immediate') => {
    if (!selectedJobId) return;
    try {
      await fetch(`/pipelines/${selectedJobId}/stop?mode=${stopMode}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      await fetchJobDetails(selectedJobId);
      await fetchJobs(selectedWorkspace);
    } catch (err) {
      console.error('Stop failed:', err);
    }
  };


  const handleReplayDLQ = async () => {
    if (!selectedJobId) return;
    try {
      await fetch(`/pipelines/${selectedJobId}/dlq/replay`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (selectedJobId) fetchJobDetails(selectedJobId);
    } catch (err) {
      console.error('Replay failed:', err);
    }
  };

  const filteredJobs = useMemo(() => {
    return jobs
      .filter((j) =>
        j.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (j.pipeline_id && j.pipeline_id.toLowerCase().includes(searchQuery.toLowerCase()))
      )
      .sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
  }, [jobs, searchQuery]);

  if (projectsLoading) {
    return (
      <div className="flex flex-col h-screen bg-slate-50 items-center justify-center font-sans">
        <div className="flex items-center gap-3 text-slate-700 font-semibold text-sm">
          <div className="w-5 h-5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
          Loading Workspace...
        </div>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="flex flex-col h-screen bg-slate-50 items-center justify-center font-sans">
        <div className="bg-white p-8 rounded-xl shadow-sm border border-slate-200 text-center max-w-md">
          <FolderGit2 className="w-12 h-12 text-indigo-600 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 mb-2">Welcome to Veloctra Data Platform</h2>
          <p className="text-sm text-slate-500 mb-6">You don't have any workspaces yet. Create a workspace to get started with your ETL pipelines.</p>
          <div className="flex flex-col gap-2">
            <button 
              onClick={() => setIsProjectModalOpen(true)}
              className="w-full px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-bold text-sm shadow-md shadow-indigo-500/20"
            >
              Create Your First Workspace
            </button>
            <button
              onClick={() => fetchProjects()}
              className="w-full px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-semibold text-xs transition-colors"
            >
              ↻ Refresh Workspaces
            </button>
            <button
              onClick={onLogout}
              className="w-full px-4 py-2 text-rose-600 hover:bg-rose-50 rounded-lg font-semibold text-xs transition-colors"
            >
              Sign Out & Re-Authenticate
            </button>
          </div>
        </div>
        <ProjectCreateModal
          isOpen={isProjectModalOpen}
          onClose={() => setIsProjectModalOpen(false)}
          token={token}
          onProjectCreated={(p) => {
            fetchProjects();
            setSelectedWorkspace(p.id);
            setIsProjectModalOpen(false);
          }}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-slate-50 text-slate-900 overflow-hidden font-sans">
      {/* Top Header Bar */}
      <header className="h-14 border-b border-slate-200 bg-white px-6 flex items-center justify-between shrink-0 z-20 shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shadow-md shadow-indigo-500/20 shrink-0">
            <Zap className="w-4 h-4 text-white" />
          </div>
          <div className="truncate min-w-0 flex items-center gap-2">
            <span className="font-bold text-base tracking-tight text-slate-900">Veloctra Data Platform</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
              v1.0 Enterprise
            </span>
          </div>
        </div>

        {/* Top Right Controls & Workspace Selector */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-100 border border-slate-200 text-xs">
            <FolderGit2 className="w-3.5 h-3.5 text-indigo-600" />
            <select
              value={selectedWorkspace}
              onChange={(e) => setSelectedWorkspace(e.target.value)}
              className="bg-transparent font-semibold text-slate-900 focus:outline-none cursor-pointer"
            >
              {projects.map((ws) => (
                <option key={ws.id} value={ws.id}>
                  {ws.name} ({ws.id})
                </option>
              ))}
            </select>
            <button
              onClick={() => setIsProjectModalOpen(true)}
              className="ml-1 px-1.5 py-0.5 rounded bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-[10px]"
              title="Create Workspace"
            >
              + New
            </button>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-100 border border-slate-200 text-xs">
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
            <span className="text-slate-700 font-semibold">
              {isConnected ? 'Live WebSocket' : 'Disconnected'}
            </span>
          </div>

          <button
            onClick={() => {
              fetchProjects();
              fetchJobs(selectedWorkspace);
              if (selectedJobId) fetchJobDetails(selectedJobId);
            }}
            className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition-colors"
            title="Refresh All"
          >
            <RefreshCw className="w-4 h-4" />
          </button>

          <button
            onClick={onLogout}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 text-xs font-semibold transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" /> Logout
          </button>
        </div>
      </header>

      {/* Main Layout Grid */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Navigation Sidebar */}
        <aside className="w-64 border-r border-slate-200 bg-white p-4 flex flex-col justify-between shrink-0 overflow-y-auto">
          <div className="space-y-6">
            {/* Group 1: MONITOR & OBSERVE */}
            <div className="space-y-1">
              <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                Monitor & Observe
              </div>
              <button
                onClick={() => handleNavClick('dashboard')}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeNav === 'dashboard'
                    ? 'bg-indigo-50 border border-indigo-200 text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <LayoutDashboard className="w-4 h-4 text-indigo-600" />
                <span>Pipeline Dashboard</span>
              </button>

              <button
                onClick={() => handleNavClick('observability')}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeNav === 'observability'
                    ? 'bg-indigo-50 border border-indigo-200 text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <Gauge className="w-4 h-4 text-purple-600" />
                <span>Observability & Reports</span>
              </button>

              <button
                onClick={() => handleNavClick('dlq')}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeNav === 'dlq'
                    ? 'bg-indigo-50 border border-indigo-200 text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                <span>Dead Letter Queue (DLQ)</span>
              </button>
            </div>

            {/* Group 2: CONFIG & MODELING */}
            <div className="space-y-1">
              <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                Connections & Design
              </div>

              <button
                onClick={() => handleNavClick('connections')}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeNav === 'connections'
                    ? 'bg-indigo-50 border border-indigo-200 text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <Plug className="w-4 h-4 text-amber-600" />
                <span>Connections Manager</span>
              </button>

              <button
                onClick={() => handleNavClick('studio')}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeNav === 'studio'
                    ? 'bg-indigo-50 border border-indigo-200 text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <Sparkles className="w-4 h-4 text-emerald-600" />
                <span>Pipeline Studio</span>
              </button>

              <button
                onClick={() => handleNavClick('bulk')}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeNav === 'bulk'
                    ? 'bg-indigo-50 border border-indigo-200 text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <UploadCloud className="w-4 h-4 text-indigo-600" />
                <span>Bulk Config Import</span>
              </button>
            </div>

            {/* Group 3: GOVERNANCE & HELP */}
            <div className="space-y-1">
              <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                Governance & Help
              </div>
              <button
                onClick={() => handleNavClick('settings')}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeNav === 'settings'
                    ? 'bg-indigo-50 border border-indigo-200 text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <Shield className="w-4 h-4 text-rose-600" />
                <span>Settings & RBAC</span>
              </button>

              <button
                onClick={() => handleNavClick('docs')}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  activeNav === 'docs'
                    ? 'bg-indigo-50 border border-indigo-200 text-indigo-700 shadow-sm'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <BookOpen className="w-4 h-4 text-cyan-600" />
                <span>Help & Usage Guide</span>
              </button>
            </div>
          </div>

          {/* Sidebar Footer Info */}
          <div className="pt-4 border-t border-slate-100 text-[11px] text-slate-400 space-y-1">
            <div>Workspace: <span className="font-mono font-semibold text-slate-700">{selectedWorkspace}</span></div>
            <div>Status: <span className="text-emerald-600 font-semibold">Active & Healthy</span></div>
          </div>
        </aside>

        {/* Secondary Pipeline Explorer Drawer (Only active when on Pipeline Dashboard) */}
        {activeNav === 'dashboard' && (
          <aside className="w-72 border-r border-slate-200 bg-white p-4 flex flex-col justify-between shrink-0 overflow-hidden shadow-sm">
            <div className="flex flex-col flex-1 overflow-hidden min-h-0 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-indigo-600" /> Pipeline Runs ({filteredJobs.length})
                </span>
                <span className="text-[10px] font-semibold text-slate-400">Latest first</span>
              </div>

              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search runs or pipelines..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:border-indigo-600 focus:bg-white transition-all"
                />
              </div>

              <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                {filteredJobs.length === 0 ? (
                  <div className="text-center py-10 px-4 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                    <Layers className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                    <p className="text-xs font-semibold text-slate-600">No runs recorded</p>
                    <p className="text-[11px] text-slate-400 mt-1">Start a pipeline run below to stream data and telemetry.</p>
                  </div>
                ) : (
                  filteredJobs.map((job) => {
                    const isSelected = selectedJobId === job.id;
                    const isActive =
                      job.state === 'EXTRACTING' ||
                      job.state === 'TRANSFORMING' ||
                      job.state === 'LOADING';

                    return (
                      <button
                        key={job.id}
                        onClick={() => setSelectedJobId(job.id)}
                        className={`w-full p-2.5 rounded-xl border text-left transition-all group flex flex-col gap-1.5 ${
                          isSelected
                            ? 'bg-indigo-50/70 border-indigo-300 shadow-sm ring-1 ring-indigo-500/20'
                            : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/60'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1.5 min-w-0">
                          <div className="flex items-center gap-1.5 min-w-0 truncate">
                            <span
                              className={`w-2 h-2 rounded-full shrink-0 ${
                                isActive
                                  ? 'bg-emerald-500 animate-ping'
                                  : job.state === 'PAUSED'
                                  ? 'bg-amber-500'
                                  : job.state === 'FAILED'
                                  ? 'bg-rose-500'
                                  : job.state === 'COMPLETED'
                                  ? 'bg-emerald-500'
                                  : 'bg-slate-400'
                              }`}
                            />
                            <span className={`font-mono text-xs truncate ${isSelected ? 'font-bold text-indigo-950' : 'font-semibold text-slate-900'}`}>
                              {job.id}
                            </span>
                          </div>
                          <span
                            className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border shrink-0 ${
                              job.state === 'COMPLETED'
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                : isActive
                                ? 'bg-cyan-50 text-cyan-700 border-cyan-200'
                                : job.state === 'FAILED'
                                ? 'bg-rose-50 text-rose-700 border-rose-200'
                                : 'bg-slate-100 text-slate-600 border-slate-200'
                            }`}
                          >
                            {job.state}
                          </span>
                        </div>

                        <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5 border-t border-slate-100/80">
                          <span className="flex items-center gap-1 font-medium">
                            <Clock className="w-3 h-3 text-slate-400" />
                            {job.created_at ? formatJobTime(job.created_at) : 'Active Run'}
                          </span>
                          {job.duration_sec !== undefined && job.duration_sec > 0 && (
                            <span className="font-mono text-[10px] text-slate-500 font-semibold">
                              ⏱️ {job.duration_sec}s
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Quick Launch Control */}
            <div className="pt-3 border-t border-slate-200 space-y-2 shrink-0">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-amber-500" /> Start Pipeline Run
              </span>
              <select
                value={selectedLaunchPipeline}
                onChange={(e) => setSelectedLaunchPipeline(e.target.value)}
                className="w-full px-2.5 py-1.5 rounded-md bg-white border border-slate-300 text-xs text-slate-900 focus:outline-none focus:border-indigo-600 font-sans"
              >
                {availablePipelines.length === 0 && <option value="" disabled>No pipelines found</option>}
                {availablePipelines.map(pid => (
                  <option key={pid} value={pid}>{pid}</option>
                ))}
              </select>
              <button
                onClick={handleStartJob}
                disabled={!selectedLaunchPipeline}
                className="w-full py-2 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-xs font-semibold flex items-center justify-center gap-1.5 shadow-sm transition-all"
              >
                <Play className="w-3.5 h-3.5" /> Launch Pipeline Run
              </button>
            </div>
          </aside>
        )}

        {/* Main Content Workspace */}
        <main className="flex-1 p-6 overflow-y-auto bg-slate-50 flex flex-col gap-6">
          {/* Dashboard View */}
          {activeNav === 'dashboard' && (
            <>
              <div className="flex items-center justify-between flex-wrap gap-2 bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
                <div>
                  <h1 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-indigo-600" />
                    <span>{selectedJobId ? `Pipeline: ${selectedJobId}` : 'Select a Pipeline'}</span>
                  </h1>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Workspace: <span className="text-slate-800 font-mono font-semibold">{selectedWorkspace}</span>
                  </p>
                </div>

                {selectedJobId && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleStopJob('rollback')}
                      className="px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 hover:bg-amber-100 text-xs font-bold flex items-center gap-1 transition-colors"
                      title="Stop pipeline & rollback uncommitted chunk checkpoints"
                    >
                      <Pause className="w-3.5 h-3.5" /> Stop & Rollback
                    </button>
                    <button
                      onClick={() => handleStopJob('immediate')}
                      className="px-3 py-1.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 hover:bg-rose-100 text-xs font-bold flex items-center gap-1 transition-colors"
                      title="Immediately cancel execution without mutating state"
                    >
                      <Pause className="w-3.5 h-3.5" /> Emergency Stop
                    </button>
                    <button
                      onClick={handleStartJob}
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold flex items-center gap-1 shadow-sm transition-colors"
                    >
                      <Play className="w-3.5 h-3.5" /> Resume / Run
                    </button>
                  </div>
                )}
              </div>

              {/* Failure Root Cause & Diagnostics Alert Banner */}
              {((currentState === 'FAILED') || (jobs.find((j) => j.id === selectedJobId)?.state === 'FAILED') || !!jobError) && (
                <div className="w-full bg-rose-50 border-2 border-rose-300 rounded-xl p-5 shadow-sm space-y-3.5 animate-in fade-in duration-200">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-rose-200/70 pb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-xl bg-rose-100 border border-rose-300 flex items-center justify-center text-rose-600 shrink-0 shadow-xs">
                        <AlertOctagon className="w-5 h-5 animate-pulse" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="px-2.5 py-0.5 rounded-full bg-rose-600 text-white font-black text-xs tracking-wider uppercase flex items-center gap-1 shadow-xs">
                            <AlertCircle className="w-3 h-3" /> Pipeline Run Failed
                          </span>
                          <span className="px-2.5 py-0.5 rounded-md bg-white border border-rose-300 text-rose-900 font-mono text-xs font-bold">
                            Failed In Stage: <strong className="text-amber-700">{jobError?.failed_at_state || currentState || 'CHECKPOINTING'}</strong>
                          </span>
                          {jobError?.error_type && (
                            <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-800 font-mono text-[11px] font-semibold">
                              {jobError.error_type}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-rose-800 font-medium mt-1">Execution halted due to an unexpected state machine violation or runtime exception.</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0 pt-1 md:pt-0">
                      <button
                        onClick={() => {
                          const text = jobError?.traceback || jobError?.message || 'Pipeline execution failed';
                          navigator.clipboard.writeText(text);
                          setCopiedError(true);
                          setTimeout(() => setCopiedError(false), 2000);
                        }}
                        className="px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 border border-rose-200 text-rose-900 text-xs font-bold flex items-center gap-1.5 shadow-xs transition-colors"
                        title="Copy error details"
                      >
                        {copiedError ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-rose-700" />}
                        {copiedError ? 'Copied!' : 'Copy Error'}
                      </button>

                      <button
                        onClick={() => setIsErrorModalOpen(true)}
                        className="px-3 py-1.5 rounded-lg bg-rose-100 hover:bg-rose-200 border border-rose-300 text-rose-900 text-xs font-bold flex items-center gap-1.5 transition-colors"
                      >
                        <Maximize2 className="w-3.5 h-3.5 text-rose-800" /> Full Diagnostics
                      </button>

                      <button
                        onClick={handleStartJob}
                        className="px-3.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold flex items-center gap-1.5 shadow transition-colors"
                      >
                        <Play className="w-3.5 h-3.5" /> Retry Run
                      </button>
                    </div>
                  </div>

                  {/* Primary Error Message Display */}
                  <div className="p-3.5 bg-white border border-rose-200 rounded-lg text-xs font-mono text-rose-950 font-semibold break-words leading-relaxed shadow-xs">
                    {jobError?.message || 'Illegal FSM transition for job: execution halted unexpectedly.'}
                  </div>

                  {/* Collapsible Quick Inline Stack Trace */}
                  {jobError?.traceback && (
                    <div className="pt-0.5">
                      <button
                        onClick={() => setIsErrorExpanded(!isErrorExpanded)}
                        className="text-xs font-bold text-rose-700 hover:text-rose-900 flex items-center gap-1.5 transition-colors"
                      >
                        {isErrorExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        {isErrorExpanded ? 'Hide Raw Stack Trace' : 'Show Complete Exception Traceback'}
                      </button>

                      {isErrorExpanded && (
                        <div className="mt-2.5 p-3.5 bg-slate-50 border border-slate-200 rounded-lg font-mono text-xs text-rose-950 max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed select-text shadow-inner">
                          {jobError.traceback}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              <MetricCards progress={progress || jobMetrics} />
              <FSMPipelineVisualizer currentState={currentState} />

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <DLQInspector
                  records={dlqRecords}
                  onReplay={handleReplayDLQ}
                  onRefresh={() => selectedJobId && fetchJobDetails(selectedJobId)}
                  jobId={selectedJobId}
                  token={token}
                />
                <CircuitBreakerMonitor breakers={circuitBreakers} />
              </div>

            </>
          )}

          {/* Connections Manager View */}
          {activeNav === 'connections' && <ConnectionsManager token={token} />}

          {/* Unified Pipeline Studio View */}
          {activeNav === 'studio' && (
            <div className="space-y-4">
              <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4 text-slate-900">
                <div>
                  <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-600" /> Pipeline Studio & Contract Designer
                  </h2>
                  <p className="text-xs text-slate-500">Design, edit, validate, version, import, and publish high-performance streaming pipelines</p>
                  
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-semibold text-slate-700">Select Pipeline:</span>
                    <select
                      value={studioPipelineId}
                      onChange={(e) => {
                        const newId = e.target.value;
                        setStudioPipelineId(newId);
                        fetchCurrentConfig(newId);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-800 font-mono shadow-2xs focus:border-indigo-600 focus:outline-none min-w-[220px]"
                    >
                      {availablePipelines.map((pid) => (
                        <option key={pid} value={pid}>{pid}</option>
                      ))}
                    </select>

                    <button
                      onClick={() => {
                        const newName = prompt('Enter New Pipeline ID:');
                        if (newName && newName.trim()) {
                          const sanitized = newName.trim().toLowerCase().replace(/[^a-z0-9_]/g, '_');
                          setStudioPipelineId(sanitized);
                          if (!availablePipelines.includes(sanitized)) {
                            setAvailablePipelines([...availablePipelines, sanitized]);
                          }
                        }
                      }}
                      className="px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-[11px] border border-slate-200 transition-colors"
                    >
                      + New
                    </button>

                    <button
                      onClick={() => setIsImportModalOpen(true)}
                      className="px-2.5 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 font-bold text-[11px] flex items-center gap-1 transition-colors"
                      title="Import YAML or JSON Pipeline Config"
                    >
                      <UploadCloud className="w-3.5 h-3.5" /> Import Pipeline
                    </button>

                    <button
                      onClick={async () => {
                        if (!studioPipelineId) return;
                        try {
                          const res = await fetch(`/configs/${studioPipelineId}/publish`, {
                            method: 'POST',
                            headers: { Authorization: `Bearer ${token}` }
                          });
                          if (res.ok) {
                            alert(`Pipeline '${studioPipelineId}' published and active in Engine!`);
                            fetchPipelines();
                          } else {
                            const err = await res.json();
                            alert(`Publish failed: ${err.detail || 'Error'}`);
                          }
                        } catch (e: any) {
                          alert(`Publish error: ${e.message}`);
                        }
                      }}
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-[11px] shadow-2xs transition-colors flex items-center gap-1"
                    >
                      <Sparkles className="w-3 h-3" /> Publish to Engine
                    </button>

                    <button
                      onClick={async () => {
                        if (!studioPipelineId) return;
                        if (!confirm(`Are you sure you want to delete pipeline '${studioPipelineId}'?`)) return;
                        try {
                          const res = await fetch(`/configs/${studioPipelineId}`, {
                            method: 'DELETE',
                            headers: { Authorization: `Bearer ${token}` }
                          });
                          if (res.ok) {
                            alert(`Pipeline '${studioPipelineId}' deleted.`);
                            fetchPipelines();
                            setStudioPipelineId(availablePipelines[0] || 'new_pipeline');
                          }
                        } catch (e: any) {
                          alert(`Delete error: ${e.message}`);
                        }
                      }}
                      className="px-2.5 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 font-bold text-[11px] transition-colors"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {/* Sub-Tabs Selector inside Studio */}
                <div className="flex items-center gap-1 bg-slate-50 p-1 rounded-lg border border-slate-200 text-xs">
                  <button
                    onClick={() => setStudioSubTab('wizard_step1')}
                    className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'wizard_step1' ? 'bg-indigo-600 text-white shadow-2xs' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <Sliders className="w-3.5 h-3.5" /> 1. System Selection
                  </button>
                  <button
                    onClick={() => setStudioSubTab('visual_modeler')}
                    className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'visual_modeler' ? 'bg-indigo-600 text-white shadow-2xs' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <Network className="w-3.5 h-3.5" /> 2. Data Modeler
                  </button>
                  <button
                    onClick={() => setStudioSubTab('consolidate')}
                    className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'consolidate' ? 'bg-indigo-600 text-white shadow-2xs' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <Layers className="w-3.5 h-3.5" /> N-Table Consolidator
                  </button>
                  <button
                    onClick={() => setStudioSubTab('mapper')}
                    className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'mapper' ? 'bg-indigo-600 text-white shadow-2xs' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <Network className="w-3.5 h-3.5" /> Schema Contract Mapper
                  </button>
                  <button
                    onClick={() => setStudioSubTab('yaml')}
                    className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'yaml' ? 'bg-indigo-600 text-white shadow-2xs' : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <FileCode className="w-3.5 h-3.5" /> YAML Editor
                  </button>
                </div>
              </div>

              {studioSubTab === 'wizard_step1' && (
                <StudioWizardStep1
                  availableConnections={connections}
                  pipelineId={studioPipelineId}
                  wizardConfig={wizardConfig}
                  onNext={(cfg) => {
                    setWizardConfig(cfg);
                    setStudioSubTab('visual_modeler');
                  }}
                />
              )}

              {studioSubTab === 'visual_modeler' && (
                <VisualDataModeler
                  token={token}
                  projectId={studioPipelineId || selectedWorkspace}
                  wizardConfig={wizardConfig}
                  availableConnections={connections}
                  schemaTables={schemaTables}
                  fieldMappings={fieldMappings}
                  setFieldMappings={setFieldMappings}
                  mappingTypes={mappingTypes}
                  schemaConnectionString={schemaConnectionString}
                  setSchemaConnectionString={setSchemaConnectionString}
                  fetchSchema={fetchSchema}
                  schemaLoading={schemaLoading}
                />
              )}

              {studioSubTab === 'consolidate' && (
                <MultiTableConsolidator
                  token={token}
                  projectId={studioPipelineId || selectedWorkspace}
                  availableConnections={connections}
                  wizardConfig={wizardConfig}
                  onSaved={() => fetchJobs(selectedWorkspace)}
                />
              )}

              {studioSubTab === 'mapper' && (
                <DataModelMapper 
                  token={token} 
                  projectId={studioPipelineId || selectedWorkspace}
                  schemaTables={schemaTables}
                  fieldMappings={fieldMappings}
                  setFieldMappings={setFieldMappings}
                  mappingTypes={mappingTypes}
                  setMappingTypes={setMappingTypes}
                  encryptedFields={encryptedFields}
                  setEncryptedFields={setEncryptedFields}
                  schemaConnectionString={schemaConnectionString}
                  setSchemaConnectionString={setSchemaConnectionString}
                  fetchSchema={fetchSchema}
                  schemaLoading={schemaLoading}
                />
              )}

              {studioSubTab === 'yaml' && (
                <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm min-h-[450px]">
                  <ConfigEditor
                    projectId={studioPipelineId || selectedWorkspace}
                    initialYaml={_configYaml}
                    token={token}
                    onSaved={() => fetchJobs(selectedWorkspace)}
                  />
                </div>
              )}
            </div>
          )}

          {/* Bulk Import View */}
          {activeNav === 'bulk' && (
            <BulkConfigUploader
              token={token}
              onUploaded={() => {
                fetchProjects();
                fetchJobs(selectedWorkspace);
              }}
            />
          )}

          {/* Observability View */}
          {activeNav === 'observability' && (
            <ObservabilityDashboard
              progress={progress || jobMetrics}
              currentState={currentState}
              auditLog={auditLog}
              dlqRecords={dlqRecords}
              onRefresh={() => selectedJobId && fetchJobDetails(selectedJobId)}
              token={token}
              projectId={selectedWorkspace}
              jobs={jobs}
              selectedJobId={selectedJobId}
              onSelectJob={(id) => {
                setSelectedJobId(id);
                fetchJobDetails(id);
              }}
            />
          )}

          {/* Settings & RBAC View */}
          {activeNav === 'settings' && <SettingsRBAC token={token} />}

          {/* Help & Documentation Guide View */}
          {activeNav === 'docs' && <PlatformDocs />}

          {/* DLQ View */}
          {activeNav === 'dlq' && (
            <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm h-[calc(100vh-140px)]">
              <DLQInspector 
                records={dlqRecords} 
                onReplay={handleReplayDLQ} 
                onRefresh={() => selectedJobId && fetchJobDetails(selectedJobId)} 
                jobId={selectedJobId} 
                token={token} 
              />
            </div>
          )}
        </main>
      </div>

      {/* Full Error Diagnostics Modal (Light Mode, Wrapped & No Horizontal Scroll) */}
      {isErrorModalOpen && jobError && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl space-y-4 p-6 text-slate-900 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-bold text-rose-700 flex items-center gap-2">
                <AlertOctagon className="w-5 h-5 text-rose-600" /> Pipeline Failure Diagnostics — {selectedJobId}
              </h3>
              <button
                onClick={() => setIsErrorModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md hover:bg-slate-100 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3.5 flex-1 overflow-y-auto overflow-x-hidden pr-1">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <div className="text-slate-500 font-bold uppercase text-[10px]">Error Type</div>
                  <div className="text-rose-800 font-mono font-bold mt-1 break-all">{jobError.error_type || 'ExecutionError'}</div>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <div className="text-slate-500 font-bold uppercase text-[10px]">Failed In Stage</div>
                  <div className="text-amber-800 font-mono font-bold mt-1 break-all">{jobError.failed_at_state || currentState || 'PROCESSING'}</div>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 col-span-2 sm:col-span-1">
                  <div className="text-slate-500 font-bold uppercase text-[10px]">Pipeline ID</div>
                  <div className="text-indigo-800 font-mono font-bold mt-1 truncate">{selectedJobId}</div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Primary Error Message</label>
                <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-lg text-rose-950 text-xs font-mono break-words break-all leading-relaxed whitespace-pre-wrap overflow-x-hidden">
                  {jobError.message}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
                    <Terminal className="w-3.5 h-3.5 text-slate-500" /> Complete Exception Stack Trace & Diagnostics
                  </label>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(jobError.traceback || jobError.message || '');
                      setCopiedError(true);
                      setTimeout(() => setCopiedError(false), 2000);
                    }}
                    className="text-xs text-indigo-700 hover:text-indigo-900 font-semibold flex items-center gap-1 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200 transition-colors"
                  >
                    {copiedError ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                    {copiedError ? 'Copied to Clipboard' : 'Copy Trace'}
                  </button>
                </div>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg font-mono text-xs text-slate-800 max-h-72 overflow-y-auto overflow-x-hidden whitespace-pre-wrap break-words break-all leading-relaxed select-text shadow-inner">
                  {jobError.traceback || jobError.message}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-slate-100 pt-3">
              <button
                onClick={() => {
                  setIsErrorModalOpen(false);
                  setActiveNav('observability');
                }}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" /> View in Observability
              </button>
              <div className="flex gap-2">
                <button
                  onClick={() => setIsErrorModalOpen(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition-colors"
                >
                  Close
                </button>
                <button
                  onClick={() => {
                    setIsErrorModalOpen(false);
                    handleStartJob();
                  }}
                  className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow transition-colors"
                >
                  <Play className="w-3.5 h-3.5" /> Retry Pipeline Run
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Import Pipeline Modal (Light Mode) */}
      {isImportModalOpen && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl space-y-4 p-6 text-slate-900 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <UploadCloud className="w-5 h-5 text-indigo-600" /> Import Streaming Pipeline Specification
              </h3>
              <button
                onClick={() => {
                  setIsImportModalOpen(false);
                  setImportStatus(null);
                }}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleImportSubmit} className="space-y-4 flex-1 overflow-y-auto pr-1">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Upload Pipeline File (.yaml or .json)</label>
                <input
                  type="file"
                  accept=".yaml,.yml,.json"
                  onChange={handleFileUpload}
                  className="w-full text-xs text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border file:border-slate-200 file:text-xs file:font-semibold file:bg-slate-50 file:text-slate-700 hover:file:bg-slate-100 cursor-pointer"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Pipeline ID (Identifier)</label>
                <input
                  type="text"
                  placeholder="e.g. postgres_to_mongo_claims"
                  value={importPipelineId}
                  onChange={(e) => setImportPipelineId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-600 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Pipeline Specification Content (YAML or JSON)</label>
                <textarea
                  rows={10}
                  placeholder={`pipeline_id: custom_pipeline\nproject_id: ${selectedWorkspace}\nversion: 1\nsources:\n  - name: pg_source\n    type: database\n    connection_string: "..."\ntransformations: []\ndestinations:\n  - name: mongo_dest\n    type: nosql\n    ...`}
                  value={importYamlText}
                  onChange={(e) => setImportYamlText(e.target.value)}
                  className="w-full p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-600 focus:bg-white resize-y"
                  required
                />
              </div>

              {importStatus && (
                <div className={`p-3 rounded-lg border text-xs font-semibold flex items-center gap-2 ${
                  importStatus.includes('Error')
                    ? 'bg-rose-50 border-rose-200 text-rose-800'
                    : 'bg-emerald-50 border-emerald-200 text-emerald-800'
                }`}>
                  {importStatus.includes('Error') ? <AlertCircle className="w-4 h-4 text-rose-600" /> : <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
                  {importStatus}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-3">
                <button
                  type="button"
                  onClick={() => {
                    setIsImportModalOpen(false);
                    setImportStatus(null);
                  }}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={importing || !importYamlText.trim()}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow transition-colors disabled:opacity-50"
                >
                  <UploadCloud className="w-3.5 h-3.5" /> {importing ? 'Importing...' : 'Save & Register Pipeline'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Project Workspace Creation Modal */}
      <ProjectCreateModal
        isOpen={isProjectModalOpen}
        onClose={() => setIsProjectModalOpen(false)}
        token={token}
        onProjectCreated={(p) => {
          fetchProjects();
          setSelectedWorkspace(p.id);
        }}
      />
    </div>
  );
};

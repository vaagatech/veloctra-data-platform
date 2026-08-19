import React, { useEffect, useState } from 'react';
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
} from 'lucide-react';
import { CircuitBreakerInfo, DLQRecord, FSMState, JobInfo } from '../types';
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
      const res = await fetch(`/configs/${pid}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setConfigYaml(JSON.stringify(data, null, 2));
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
  const [schemaConnectionString, setSchemaConnectionString] = useState('sqlite:///demo_source_nm.db');
  const [schemaLoading, setSchemaLoading] = useState(false);

  const fetchSchema = async () => {
    setSchemaLoading(true);
    try {
      const res = await fetch('/configs/schema-discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ connection_string: schemaConnectionString }),
      });
      if (res.ok) {
        const data = await res.json();
        const tables = data.tables || [];
        setSchemaTables(tables);
        
        // Auto-initialize mappings if not already set
        if (Object.keys(fieldMappings).length === 0 && tables.length > 0) {
          const initialMap: Record<string, string> = {};
          const initialTypes: Record<string, 'direct' | 'function'> = {};
          const initialEnc: Record<string, boolean> = {};
          
          tables.forEach((tbl: any) => {
            (tbl.columns || []).forEach((c: string) => {
              const key = `${tbl.table_name}.${c}`;
              initialMap[key] = c; // default map to same name
              initialTypes[key] = 'direct';
              initialEnc[key] = c.includes('ssn') || c.includes('card');
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

  const fetchProjects = async () => {
    try {
      const res = await fetch('/projects', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const fetchedProjects = data.projects || [];
        setProjects(fetchedProjects);
        if (fetchedProjects.length === 0) {
          setIsProjectModalOpen(true);
        } else if (!selectedWorkspace) {
          setSelectedWorkspace(fetchedProjects[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch projects:', err);
    }
  };

  const fetchPipelines = async () => {
    if (!selectedWorkspace) return;
    try {
      const res = await fetch('/configs/list', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAvailablePipelines(data.pipelines || []);
        if (data.pipelines && data.pipelines.length > 0) {
          setSelectedLaunchPipeline(data.pipelines[0]);
        }
      }
    } catch (err) {
      console.error('Failed to fetch pipelines:', err);
    }
  };

  const fetchConnections = async () => {
    if (!selectedWorkspace) return;
    try {
      const res = await fetch('/configs/connections/list', {
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
      const res = await fetch(`/pipelines?project_id=${ws}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) {
        onLogout();
        return;
      }
      const data = await res.json();
      const jobList: JobInfo[] = Object.entries(data.jobs || {}).map(([id, state]) => ({
        id,
        state: state as FSMState,
      }));
      setJobs(jobList);
      if (jobList.length > 0) {
        setSelectedJobId(jobList[0].id);
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

  const filteredJobs = jobs.filter((j) =>
    j.id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (projects.length === 0) {
    return (
      <div className="flex flex-col h-screen bg-slate-50 items-center justify-center font-sans">
        <div className="bg-white p-8 rounded-xl shadow-sm border border-slate-200 text-center max-w-md">
          <FolderGit2 className="w-12 h-12 text-indigo-600 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 mb-2">Welcome to Veloctra Data Platform</h2>
          <p className="text-sm text-slate-500 mb-6">You don't have any workspaces yet. Create a workspace to get started with your ETL pipelines.</p>
          <button 
            onClick={() => setIsProjectModalOpen(true)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-bold text-sm"
          >
            Create Your First Workspace
          </button>
        </div>
        <ProjectCreateModal
          isOpen={isProjectModalOpen}
          onClose={() => {}} // Forced, cannot close
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
                  {ws.name}
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
          <aside className="w-64 border-r border-slate-200 bg-slate-50/50 p-4 flex flex-col justify-between shrink-0 overflow-hidden">
            <div className="flex flex-col flex-1 overflow-hidden min-h-0 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-purple-600" /> Workspace Pipelines ({filteredJobs.length})
                </span>
              </div>

              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Search pipelines..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 rounded-md bg-white border border-slate-300 text-xs text-slate-900 focus:outline-none focus:border-indigo-600"
                />
              </div>

              <div className="flex-1 overflow-y-auto space-y-1 pr-1">
                {filteredJobs.length === 0 ? (
                  <div className="text-center py-8 text-xs text-slate-400">
                    No active pipelines in this workspace
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
                        className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-all text-left group min-w-0 ${
                          isSelected
                            ? 'bg-white border border-indigo-200 text-indigo-900 font-bold shadow-sm'
                            : 'hover:bg-white/60 text-slate-600'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0 truncate">
                          <span
                            className={`w-2 h-2 rounded-full shrink-0 ${
                              isActive
                                ? 'bg-emerald-500 animate-pulse'
                                : job.state === 'PAUSED'
                                ? 'bg-amber-500'
                                : job.state === 'FAILED'
                                ? 'bg-rose-500'
                                : 'bg-slate-400'
                            }`}
                          />
                          <span className="truncate font-mono text-[11px]">{job.id}</span>
                        </div>
                        <span className="text-[10px] font-sans uppercase px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 shrink-0 ml-1">
                          {job.state}
                        </span>
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

              <MetricCards progress={progress} />
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
              <div className="bg-slate-900/90 p-4 rounded-xl border border-slate-800 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div>
                  <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-cyan-400" /> Pipeline Studio & Contract Designer
                  </h2>
                  <p className="text-xs text-slate-400">Design, edit, validate, version, and publish high-performance streaming pipelines</p>
                  
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-semibold text-slate-300">Select Pipeline:</span>
                    <select
                      value={studioPipelineId}
                      onChange={(e) => {
                        const newId = e.target.value;
                        setStudioPipelineId(newId);
                        fetchCurrentConfig(newId);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 font-mono shadow-sm focus:border-cyan-500 focus:outline-none min-w-[220px]"
                    >
                      {availablePipelines.map((pid) => (
                        <option key={pid} value={pid}>{pid}</option>
                      ))}
                      <option value="csv_to_postgres">csv_to_postgres</option>
                      <option value="postgres_to_mongo">postgres_to_mongo</option>
                      <option value="postgres_to_csv">postgres_to_csv</option>
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
                      className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-[11px] transition-colors"
                    >
                      + New
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
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[11px] shadow transition-colors flex items-center gap-1"
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
                      className="px-2.5 py-1.5 rounded-lg bg-rose-900/40 hover:bg-rose-800/60 border border-rose-700/50 text-rose-300 font-bold text-[11px] transition-colors"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {/* Sub-Tabs Selector inside Studio */}
                <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
                  <button
                    onClick={() => setStudioSubTab('wizard_step1')}
                    className={`px-3 py-1 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'wizard_step1' ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Sliders className="w-3.5 h-3.5" /> 1. System Selection
                  </button>
                  <button
                    onClick={() => setStudioSubTab('visual_modeler')}
                    className={`px-3 py-1 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'visual_modeler' ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Network className="w-3.5 h-3.5" /> 2. Data Modeler
                  </button>
                  <button
                    onClick={() => setStudioSubTab('consolidate')}
                    className={`px-3 py-1 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'consolidate' ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Layers className="w-3.5 h-3.5 text-emerald-400" /> N-Table Consolidator
                  </button>
                  <button
                    onClick={() => setStudioSubTab('mapper')}
                    className={`px-3 py-1 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'mapper' ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <Network className="w-3.5 h-3.5" /> Schema Contract Mapper
                  </button>
                  <button
                    onClick={() => setStudioSubTab('yaml')}
                    className={`px-3 py-1 rounded-md text-xs font-bold transition-all flex items-center gap-1.5 ${
                      studioSubTab === 'yaml' ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <FileCode className="w-3.5 h-3.5" /> YAML Editor
                  </button>
                </div>
              </div>

              {studioSubTab === 'wizard_step1' && (
                <StudioWizardStep1
                  availableConnections={connections}
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
              progress={progress}
              currentState={currentState}
              auditLog={auditLog}
              dlqRecords={dlqRecords}
              onRefresh={() => selectedJobId && fetchJobDetails(selectedJobId)}
              token={token}
              projectId={selectedWorkspace}
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

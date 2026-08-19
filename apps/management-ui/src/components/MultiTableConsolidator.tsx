import React, { useState } from 'react';
import { Layers, Database, CheckCircle2, Search, Table, Save } from 'lucide-react';


interface MultiTableConsolidatorProps {
  token: string;
  projectId: string;
  onSaved: () => void;
}

export const MultiTableConsolidator: React.FC<MultiTableConsolidatorProps> = ({
  token,
  projectId,
  onSaved,
}) => {
  const [connectionString, setConnectionString] = useState('sqlite:///demo_source_nm.db');
  const [targetCollection, setTargetCollection] = useState('unified_enterprise_orders_store');
  const [discovering, setDiscovering] = useState(false);
  const [discoveredTables, setDiscoveredTables] = useState<any[]>([]);
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const handleDiscoverSchema = async () => {
    setDiscovering(true);
    setStatusMsg(null);
    try {
      const res = await fetch('/configs/schema-discover', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ connection_string: connectionString }),
      });

      if (res.ok) {
        const data = await res.json();
        setDiscoveredTables(data.tables || []);
        setSelectedTables((data.tables || []).map((t: any) => t.table_name));
        setStatusMsg(`Discovered ${data.total_tables_found} tables in source schema!`);
      }
    } catch (err: any) {
      setStatusMsg(`Discovery error: ${err.message}`);
    } finally {
      setDiscovering(false);
    }
  };

  const toggleSelectTable = (tblName: string) => {
    if (selectedTables.includes(tblName)) {
      setSelectedTables(selectedTables.filter((t) => t !== tblName));
    } else {
      setSelectedTables([...selectedTables, tblName]);
    }
  };

  const handleSaveConsolidationPipeline = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setStatusMsg(null);

    const pipelineSpec = {
      project_id: projectId,
      pipeline_id: `${projectId}_ntable_mongo_consolidator`,
      name: `${selectedTables.length}-Table Schema Auto-Consolidator to MongoDB`,
      mode: 'hybrid',
      sources: selectedTables.map((tbl) => ({
        name: tbl,
        type: 'database',
        connection_string: connectionString,
        query: `SELECT * FROM ${tbl}`,
      })),
      transformations: [],
      destinations: [
        {
          name: 'target_mongodb_unified',
          type: 'nosql',
          connection_string: 'mongodb://localhost:27017',
          collection: targetCollection,
          upsert_key: 'order_id',
        },
      ],
    };

    try {
      const yamlStr = JSON.stringify(pipelineSpec, null, 2);
      const res = await fetch(`/configs/${projectId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ yaml_content: yamlStr }),
      });

      if (!res.ok) throw new Error('Failed to save consolidation pipeline');

      setStatusMsg(`Successfully configured ${selectedTables.length}-Table Consolidation pipeline to MongoDB collection '${targetCollection}'!`);
      onSaved();
    } catch (err: any) {
      setStatusMsg(`Error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const filteredTables = discoveredTables.filter((t) =>
    t.table_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Layers className="w-4 h-4 text-emerald-600" /> N-Table Multi-Schema Auto-Consolidator
          </h3>
          <p className="text-xs text-slate-500">Auto-discover N relational tables from DSN and extract them for ingestion into a unified MongoDB target</p>
        </div>
        <span className="px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 font-bold text-xs border border-emerald-200">
          N-Table Schema Merger
        </span>
      </div>

      <form onSubmit={handleSaveConsolidationPipeline} className="space-y-6">
        {/* Step 1: Sources & Destinations */}
        <div className="space-y-4">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 border-b border-slate-100 pb-2">1. Source & Destination Connections</h4>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Source Schema DSN</label>
            <input
              type="text"
              placeholder="sqlite:///demo_source_nm.db or postgresql+asyncpg://..."
              value={connectionString}
              onChange={(e) => setConnectionString(e.target.value)}
              className="flex-1 px-3 py-2 rounded-lg bg-slate-50 border border-slate-300 text-xs font-mono text-slate-900"
              required
            />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Target MongoDB Collection</label>
              <input
                type="text"
                value={targetCollection}
                onChange={(e) => setTargetCollection(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-50 border border-slate-300 text-xs font-mono text-slate-900"
                required
              />
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <label className="block text-[10px] font-semibold text-slate-500 mb-1">Target Connection System</label>
              <input
                type="text"
                value="mongodb://localhost:27017 (Local MongoDB Cluster)"
                disabled
                className="w-full px-3 py-2 rounded-lg bg-slate-100 border border-slate-200 text-xs font-semibold text-slate-700"
              />
            </div>
            <div className="shrink-0 flex items-end pt-5">
              <button
                type="button"
                onClick={handleDiscoverSchema}
                disabled={discovering}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-sm flex items-center gap-1.5"
              >
                <Database className="w-3.5 h-3.5" /> {discovering ? 'Discovering Schema...' : 'Auto-Discover N Tables'}
              </button>
            </div>
          </div>
        </div>

        {/* Step 2: Bulk Table Selection */}
        {discoveredTables.length > 0 && (
          <div className="space-y-3 pt-4 border-t border-slate-100">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-2 border-b border-slate-100 pb-2">
                <Table className="w-4 h-4 text-indigo-600" /> 2. Bulk Edit: Table Extraction Selection ({selectedTables.length}/{discoveredTables.length} Selected)
              </h4>

              <div className="relative w-64">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Filter tables..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-8 pr-3 py-1 rounded-md bg-slate-50 border border-slate-300 text-xs text-slate-900"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2.5 max-h-60 overflow-y-auto p-2 bg-slate-50 rounded-xl border border-slate-200">
              {filteredTables.map((tbl) => {
                const isSelected = selectedTables.includes(tbl.table_name);
                return (
                  <button
                    key={tbl.table_name}
                    type="button"
                    onClick={() => toggleSelectTable(tbl.table_name)}
                    className={`p-2.5 rounded-lg border text-left flex items-start justify-between transition-all ${
                      isSelected
                        ? 'bg-white border-indigo-600 shadow-sm ring-1 ring-indigo-600'
                        : 'bg-white/60 border-slate-200 opacity-60 hover:opacity-100'
                    }`}
                  >
                    <div>
                      <div className="text-xs font-bold text-slate-900 font-mono">{tbl.table_name}</div>
                      <div className="text-[10px] text-slate-500">{tbl.rows_count.toLocaleString()} rows • {tbl.columns.length} cols</div>
                    </div>
                    {isSelected && <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}



        {/* Save & Deploy Controls */}
        <div className="flex items-center justify-between pt-4 border-t border-slate-100">
          {statusMsg ? (
            <div className="text-xs font-semibold text-emerald-700 flex items-center gap-1.5 bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-200">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" /> {statusMsg}
            </div>
          ) : (
            <div className="text-xs text-slate-400">Merges N relational tables into 1 MongoDB Document</div>
          )}

          <button
            type="submit"
            disabled={saving || selectedTables.length === 0}
            className="py-2.5 px-6 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-md shadow-emerald-500/20 flex items-center gap-2 transition-all disabled:opacity-50"
          >
            <Save className="w-4 h-4" /> {saving ? 'Deploying...' : `Deploy ${selectedTables.length}-Table MongoDB Consolidation`}
          </button>
        </div>
      </form>
    </div>
  );
};

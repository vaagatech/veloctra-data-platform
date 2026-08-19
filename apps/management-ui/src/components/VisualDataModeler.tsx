import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Sparkles, ArrowRight, Code, Key, Link2, Database, Save } from 'lucide-react';
import { ReactFlow, Controls, Background, applyNodeChanges, applyEdgeChanges, Node, Edge, Connection, NodeChange, EdgeChange, Handle, Position } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { ConnectionItem } from '../types';

interface VisualDataModelerProps {
  token: string;
  projectId: string;
  wizardConfig: any;
  availableConnections: ConnectionItem[];
  schemaTables: any[];
  fieldMappings: Record<string, string>;
  setFieldMappings: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  mappingTypes: Record<string, 'direct' | 'function'>;
  schemaConnectionString: string;
  setSchemaConnectionString: React.Dispatch<React.SetStateAction<string>>;
  fetchSchema: () => Promise<void>;
  schemaLoading: boolean;
}

// Custom Node for Database Tables
const TableNode = ({ data }: any) => {
  return (
    <div className="bg-white rounded-lg shadow-md border border-slate-200 min-w-[200px] text-xs font-mono">
      <div className="bg-indigo-600 text-white px-3 py-2 rounded-t-lg font-bold flex justify-between items-center">
        <span>{data.label}</span>
        <span className="text-[10px] bg-indigo-800 px-1.5 py-0.5 rounded opacity-80">{data.rows} rows</span>
      </div>
      <div className="p-2 space-y-1">
        {data.columns.map((col: string) => {
          const isPK = (data.primary_keys || []).includes(col);
          const fk = (data.foreign_keys || []).find((f: any) => f.column === col);
          const isFK = !!fk;
          
          return (
            <div key={col} className={`flex justify-between items-center relative py-1 hover:bg-slate-50 rounded px-1 group ${isPK ? 'bg-amber-50/50' : ''} ${isFK ? 'bg-blue-50/50' : ''}`}>
              <div className="flex items-center gap-1.5">
                {isPK && <Key className="w-3 h-3 text-amber-500" />}
                {isFK && <span title={`References ${fk.references_table}`}><Link2 className="w-3 h-3 text-blue-500" /></span>}
                <span className={`text-slate-700 ${isPK ? 'font-bold text-slate-900' : ''}`}>{col}</span>
              </div>
              <span className="text-[9px] text-slate-400 ml-2">
                {isPK ? 'PK' : isFK ? `FK -> ${fk.references_table}` : 'VARCHAR'}
              </span>
              <Handle 
                type="source" 
                position={Position.Right} 
                id={`${data.label}.${col}`}
                className="w-2 h-2 !bg-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity" 
                style={{ top: '50%', right: '-8px' }} 
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};

// Custom Node for Document Destination
const DocumentNode = ({ data }: any) => {
  return (
    <div className="bg-white rounded-lg shadow-md border-2 border-emerald-500 min-w-[250px] text-xs font-mono">
      <div className="bg-emerald-500 text-white px-3 py-2 rounded-t-sm font-bold flex justify-between items-center">
        <span>{data.label}</span>
        <span className="text-[10px] bg-emerald-700 px-1.5 py-0.5 rounded opacity-80">Document (JSON)</span>
      </div>
      <div className="p-2 space-y-1">
        {data.fields.map((field: any) => (
          <div key={field.name} className="flex items-center relative py-1 hover:bg-emerald-50 rounded px-1 group">
            <Handle 
              type="target" 
              position={Position.Left} 
              id={`target.${field.name}`}
              className="w-2 h-2 !bg-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity" 
              style={{ top: '50%', left: '-8px' }} 
            />
            <span className="text-emerald-900 font-semibold">{field.name}</span>
            <span className="text-[9px] text-emerald-600 ml-auto">{field.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const nodeTypes = {
  tableNode: TableNode,
  documentNode: DocumentNode,
};

export const VisualDataModeler: React.FC<VisualDataModelerProps> = ({ 
  token, projectId, wizardConfig, availableConnections, fieldMappings, setFieldMappings
}) => {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [transformationFunctions, setTransformationFunctions] = useState<Record<string, string>>({});
  
  // Internal schema states
  const [internalSchemaTables, setInternalSchemaTables] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Queries for configurations
  const [primaryConfigs, setPrimaryConfigs] = useState<{connection_id: string, query: string}[]>([]);
  const [secondaryConfigs, setSecondaryConfigs] = useState<any[]>([]);
  const [destConfigs, setDestConfigs] = useState<any[]>([]);
  
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  useEffect(() => {
    if (wizardConfig) {
      if (wizardConfig.primarySources) {
        setPrimaryConfigs(wizardConfig.primarySources.map((s: any) => ({ connection_id: s.connection_id, query: '' })));
      }
      if (wizardConfig.secondarySources) {
        setSecondaryConfigs(wizardConfig.secondarySources.map((s: any) => ({
          connection_id: s.connection_id,
          query: '',
          join_key: '',
          target_field: '_flatten_'
        })));
      }setDestConfigs(wizardConfig.destinations.map((d: any) => ({
        ...d,
        table_or_collection: '',
        condition: ''
      })));
    }
  }, [wizardConfig]);

  const handleFetchSchemas = async () => {
    setIsLoading(true);
    let allTables: any[] = [];
    
    const fetchForConnId = async (connId: string, prefix: string) => {
      const conn = availableConnections.find(c => c.id === connId);
      if (!conn) return;
      try {
        const res = await fetch('/configs/schema-discover', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ connection_string: conn.dsn_or_url }),
        });
        if (res.ok) {
          const data = await res.json();
          // prefix table names so they don't collide
          const tables = (data.tables || []).map((t: any) => ({
            ...t,
            table_name: `${prefix}_${t.table_name}`
          }));
          allTables = [...allTables, ...tables];
        }
      } catch (err) {
        console.error("Schema fetch error", err);
      }
    };

    if (wizardConfig?.primarySources) {
      for (let i = 0; i < wizardConfig.primarySources.length; i++) {
        await fetchForConnId(wizardConfig.primarySources[i].connection_id, `primary_${i}`);
      }
    }
    if (wizardConfig?.secondarySources) {
      for (let i = 0; i < wizardConfig.secondarySources.length; i++) {
        await fetchForConnId(wizardConfig.secondarySources[i].connection_id, `enrich_${i}`);
      }
    }

    setInternalSchemaTables(allTables);
    setIsLoading(false);
  };

  const handleSavePipeline = async () => {
    if (!wizardConfig || !projectId) return;
    setSaveStatus("Saving...");
    
    
    const configObj = {
      project_id: "default_workspace", // Or whatever we can pass, ideally selectedWorkspace
      pipeline_id: projectId,
      mode: "hybrid",
      sources: primaryConfigs.map(p => {
        const c = availableConnections.find(conn => conn.id === p.connection_id);
        return {
          type: c?.type || "database",
          connection_id: c?.id,
          connection_string: c?.dsn_or_url,
          query: p.query,
          chunk_size: 5000
        };
      }),
      enrichments: secondaryConfigs.map(s => {
        const c = availableConnections.find(conn => conn.id === s.connection_id);
        return {
          source: {
            type: c?.type || "database",
            connection_id: c?.id,
            connection_string: c?.dsn_or_url,
            table: s.query, // using query field as table/collection for enrichments
          },
          join_key: s.join_key,
          target_field: s.target_field
        };
      }),
      destinations: destConfigs.map(d => {
        const c = availableConnections.find(conn => conn.id === d.connection_id);
        return {
          name: c?.id,
          type: c?.type || "database",
          connection_string: c?.dsn_or_url,
          table: d.table_or_collection,
          condition: d.condition,
          match_keys: ['id']
        };
      }),
      mappings: fieldMappings
    };

    try {
      const yamlStr = JSON.stringify(configObj, null, 2);
      const pipelineId = wizardConfig.pipelineId || 'default_pipeline';
      const res = await fetch(`/configs/${pipelineId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ yaml_content: yamlStr }),
      });

      if (!res.ok) {
        throw new Error('Save failed');
      }
      setSaveStatus("Saved successfully!");
    } catch (err: any) {
      setSaveStatus(`Error: ${err.message}`);
    }
  };


  useEffect(() => {
    const initialNodes: Node[] = [];
    let yOffset = 50;

    (internalSchemaTables || []).forEach((tbl: any) => {
      initialNodes.push({
        id: `source-${tbl.table_name}`,
        type: 'tableNode',
        position: { x: 50, y: yOffset },
        data: { 
          label: tbl.table_name, 
          columns: tbl.columns, 
          rows: tbl.rows_count,
          primary_keys: tbl.primary_keys || [],
          foreign_keys: tbl.foreign_keys || []
        },
      });
      yOffset += 40 + (tbl.columns.length * 28) + 20;
    });

    const uniqueTargetFields = Array.from(new Set(Object.values(fieldMappings)));
    if (uniqueTargetFields.length === 0) {
        uniqueTargetFields.push('id');
    }

    initialNodes.push({
      id: 'target-document',
      type: 'documentNode',
      position: { x: 600, y: 150 },
      data: { 
        label: 'Destination Schema', 
        fields: uniqueTargetFields.map(f => ({ name: f, type: 'Mixed' }))
      },
    });

    setNodes(initialNodes);

    const newEdges: Edge[] = [];
    Object.entries(fieldMappings).forEach(([sourceKey, targetField]) => {
        const [tableName, colName] = sourceKey.split('.');
        if (tableName && colName) {
            newEdges.push({
                id: `e-${sourceKey}-${targetField}`,
                source: `source-${tableName}`,
                target: 'target-document',
                sourceHandle: sourceKey,
                targetHandle: `target.${targetField}`,
                animated: true,
                style: { stroke: '#4f46e5', strokeWidth: 2 }
            });
        }
    });
    setEdges(newEdges);
  }, [internalSchemaTables, fieldMappings]);

  const onNodesChange = useCallback((changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)), []);
  const onEdgesChange = useCallback((changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)), []);
  
  const onConnect = useCallback((params: Connection) => {
    if (params.sourceHandle && params.targetHandle) {
      const sourceCol = params.sourceHandle;
      const targetField = params.targetHandle.replace('target.', '');
      setFieldMappings(prev => ({ ...prev, [sourceCol]: targetField }));
    }
  }, [setFieldMappings]);

  const handleEdgeClick = (event: React.MouseEvent, edge: Edge) => {
    event.stopPropagation();
    setSelectedEdge(edge);
  };

  const handlePaneClick = () => {
    setSelectedEdge(null);
  };

  const updateFunction = (val: string) => {
    if (selectedEdge) {
      setTransformationFunctions(prev => ({ ...prev, [selectedEdge.id]: val }));
    }
  };

  if (!wizardConfig) {
    return <div className="p-8 text-center text-slate-500">Please complete Step 1 first.</div>;
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-[900px]">
      
      {/* Step 2 Config Panel */}
      <div className="p-4 border-b border-slate-100 bg-slate-50 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Database className="w-4 h-4 text-indigo-600" /> Step 2: Data Extraction & Routing
          </h3>
          <div className="flex gap-2">
            <button onClick={handleFetchSchemas} className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 text-xs font-bold text-slate-700 flex items-center gap-1.5 shadow-sm hover:bg-slate-50">
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} /> Fetch Schemas
            </button>
            <button onClick={handleSavePipeline} className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm hover:bg-indigo-700">
              <Save className="w-3.5 h-3.5" /> Save Pipeline
            </button>
          </div>
        </div>

        {saveStatus && (
          <div className="text-xs font-bold text-emerald-600 bg-emerald-50 border border-emerald-100 p-2 rounded">
            {saveStatus}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="bg-white p-3 rounded-lg border border-slate-200 overflow-y-auto max-h-48">
            <h4 className="text-xs font-bold text-slate-700 mb-2">Primary Sources</h4>
            {primaryConfigs.map((p, i) => (
              <div key={i} className="mb-3 space-y-1.5 pb-3 border-b border-slate-100 last:border-0">
                <span className="text-[10px] font-bold text-indigo-600">{p.connection_id}</span>
                <input 
                  type="text" 
                  placeholder="SQL Query / Collection" 
                  value={p.query}
                  onChange={(e) => { const copy = [...primaryConfigs]; copy[i].query = e.target.value; setPrimaryConfigs(copy); }}
                  className="w-full px-2 py-1.5 text-xs border border-slate-300 rounded font-mono"
                />
              </div>
            ))}
          </div>

          <div className="bg-white p-3 rounded-lg border border-slate-200 overflow-y-auto max-h-48">
            <h4 className="text-xs font-bold text-slate-700 mb-2">Enrichments</h4>
            {secondaryConfigs.length === 0 && <span className="text-xs text-slate-400">None</span>}
            {secondaryConfigs.map((s, i) => (
              <div key={i} className="mb-3 space-y-1.5 pb-3 border-b border-slate-100 last:border-0">
                <span className="text-[10px] font-bold text-indigo-600">{s.connection_id}</span>
                <input 
                  type="text" placeholder="Table / Collection" value={s.query} 
                  onChange={(e) => { const copy = [...secondaryConfigs]; copy[i].query = e.target.value; setSecondaryConfigs(copy); }}
                  className="w-full px-2 py-1 text-xs border border-slate-300 rounded font-mono"
                />
                <div className="flex gap-1.5">
                  <input 
                    type="text" placeholder="Join Key" value={s.join_key}
                    onChange={(e) => { const copy = [...secondaryConfigs]; copy[i].join_key = e.target.value; setSecondaryConfigs(copy); }}
                    className="w-1/2 px-2 py-1 text-xs border border-slate-300 rounded font-mono"
                  />
                  <input 
                    type="text" placeholder="Target Field (_flatten_)" value={s.target_field}
                    onChange={(e) => { const copy = [...secondaryConfigs]; copy[i].target_field = e.target.value; setSecondaryConfigs(copy); }}
                    className="w-1/2 px-2 py-1 text-xs border border-slate-300 rounded font-mono"
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="bg-white p-3 rounded-lg border border-slate-200 overflow-y-auto max-h-48">
            <h4 className="text-xs font-bold text-slate-700 mb-2">Destinations</h4>
            {destConfigs.map((d, i) => (
              <div key={i} className="mb-3 space-y-1.5 pb-3 border-b border-slate-100 last:border-0">
                <span className="text-[10px] font-bold text-emerald-600">{d.connection_id}</span>
                <input 
                  type="text" placeholder="Table / Collection" value={d.table_or_collection}
                  onChange={(e) => { const copy = [...destConfigs]; copy[i].table_or_collection = e.target.value; setDestConfigs(copy); }}
                  className="w-full px-2 py-1 text-xs border border-slate-300 rounded font-mono"
                />
                <input 
                  type="text" placeholder="Condition (e.g. status == 'ACT')" value={d.condition}
                  onChange={(e) => { const copy = [...destConfigs]; copy[i].condition = e.target.value; setDestConfigs(copy); }}
                  className="w-full px-2 py-1 text-xs border border-slate-300 rounded font-mono"
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div className="flex-1 relative flex">
        <div className="flex-1 h-full">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onEdgeClick={handleEdgeClick}
            onPaneClick={handlePaneClick}
            nodeTypes={nodeTypes}
            fitView
            className="bg-slate-50"
          >
            <Background color="#cbd5e1" gap={16} />
            <Controls />
          </ReactFlow>
        </div>

        {/* Function Editor Panel */}
        {selectedEdge && (
          <div className="w-80 bg-white border-l border-slate-200 p-4 flex flex-col shadow-lg z-10 absolute right-0 top-0 bottom-0 animate-in slide-in-from-right-4 duration-200">
            <h4 className="text-xs font-bold text-slate-800 flex items-center gap-1.5 mb-1">
              <Code className="w-3.5 h-3.5 text-indigo-600" /> Transformation Function
            </h4>
            <p className="text-[10px] text-slate-500 mb-4 font-mono break-all bg-slate-50 p-1.5 rounded">
              {selectedEdge.sourceHandle} <ArrowRight className="inline w-3 h-3" /> {selectedEdge.targetHandle}
            </p>

            <div className="flex-1 flex flex-col">
              <label className="text-[10px] font-semibold text-slate-700 mb-1">Python Lambda / Veloctra Function</label>
              <textarea
                value={transformationFunctions[selectedEdge.id] || "def transform(val):\n    return val"}
                onChange={(e) => updateFunction(e.target.value)}
                className="w-full flex-1 p-2 bg-slate-900 text-emerald-400 font-mono text-xs rounded-lg border border-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
                placeholder="def transform(val):&#10;    return val"
              />
            </div>
            
            <button className="mt-4 w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold flex items-center justify-center gap-2">
              <Sparkles className="w-3.5 h-3.5" /> Save Mapping Rule
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

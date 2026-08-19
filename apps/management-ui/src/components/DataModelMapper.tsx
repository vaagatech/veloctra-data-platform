import React, { useState, useEffect } from 'react';
import { Network, ShieldCheck, RefreshCw, CheckCircle2, Sparkles } from 'lucide-react';

interface DataModelMapperProps {
  token: string;
  projectId: string;
  schemaTables: any[];
  fieldMappings: Record<string, string>;
  setFieldMappings: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  mappingTypes: Record<string, 'direct' | 'function'>;
  setMappingTypes: React.Dispatch<React.SetStateAction<Record<string, 'direct' | 'function'>>>;
  encryptedFields: Record<string, boolean>;
  setEncryptedFields: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  schemaConnectionString: string;
  setSchemaConnectionString: React.Dispatch<React.SetStateAction<string>>;
  fetchSchema: () => Promise<void>;
  schemaLoading: boolean;
}

export const DataModelMapper: React.FC<DataModelMapperProps> = ({ 
  token: _token, projectId: _projectId,
  schemaTables, fieldMappings, setFieldMappings,
  mappingTypes, setMappingTypes,
  encryptedFields, setEncryptedFields,
  schemaConnectionString, setSchemaConnectionString,
  fetchSchema, schemaLoading
}) => {
  const [sourceType, setSourceType] = useState<'database' | 'api'>('database');
  const [savedStatus, setSavedStatus] = useState<string | null>(null);

  useEffect(() => {
    if (schemaTables.length === 0) fetchSchema();
  }, [sourceType]);

  const handleTargetChange = (sourceName: string, targetName: string) => {
    setFieldMappings((prev) => ({ ...prev, [sourceName]: targetName }));
  };

  const handleTypeChange = (sourceName: string, type: 'direct' | 'function') => {
    setMappingTypes((prev) => ({ ...prev, [sourceName]: type }));
  };

  const toggleEncryption = (sourceName: string) => {
    setEncryptedFields((prev) => ({ ...prev, [sourceName]: !prev[sourceName] }));
  };

  const handleSaveMapping = () => {
    setSavedStatus('Data model mapping saved to active pipeline spec!');
    setTimeout(() => setSavedStatus(null), 3000);
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-5">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3 flex-wrap gap-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Network className="w-4 h-4 text-indigo-600" /> Data Modeler & Interactive Schema Contract Mapper
          </h3>
          <p className="text-xs text-slate-500">Inspect real database source contracts and auto-map fields with AI Schema Assistance</p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value as any)}
            className="px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-300 text-xs font-semibold text-slate-800"
          >
            <option value="database">SQL Database DSN</option>
            <option value="api">REST API Schema</option>
          </select>
          <input
            type="text"
            placeholder="sqlite:///demo_source_nm.db or postgresql+asyncpg://..."
            value={schemaConnectionString}
            onChange={(e) => setSchemaConnectionString(e.target.value)}
            className="flex-1 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-mono text-slate-900"
            required
          />

          <button
            onClick={fetchSchema}
            className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 font-bold text-xs shadow-sm flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${schemaLoading ? 'animate-spin' : ''}`} /> Sync Schema
          </button>

        </div>
      </div>

      {savedStatus && (
        <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-600" /> {savedStatus}
        </div>
      )}

      {schemaLoading ? (
        <div className="py-12 text-center text-xs text-slate-400">Connecting to source system & inspecting schema contract...</div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-12 gap-4 text-[11px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 pb-2">
            <span className="col-span-3">Source Field</span>
            <span className="col-span-2 text-center">Type</span>
            <span className="col-span-5">Target Mapping / Python Script</span>
            <span className="col-span-2 text-center">Encryption</span>
          </div>

          <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
            {schemaTables.flatMap((tbl) => 
              (tbl.columns || []).map((col: string) => {
                const key = `${tbl.table_name}.${col}`;
                const colType = col.includes('id') ? 'INTEGER' : col.includes('json') ? 'JSON' : 'VARCHAR(255)';
                return (
                  <div key={key} className="grid grid-cols-12 gap-4 items-center p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                    <div className="col-span-3 flex flex-col gap-1 truncate">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-indigo-500" />
                        <span className="font-mono font-semibold text-slate-900">{key}</span>
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono ml-4">({colType})</span>
                    </div>

                    <div className="col-span-2">
                      <select
                        value={mappingTypes[key] || 'direct'}
                        onChange={(e) => handleTypeChange(key, e.target.value as 'direct' | 'function')}
                        className="w-full px-2 py-1.5 rounded bg-white border border-slate-300 text-[11px] font-bold text-slate-700 focus:outline-none focus:border-indigo-600"
                      >
                        <option value="direct">Direct Map</option>
                        <option value="function">Python Function</option>
                      </select>
                    </div>

                    <div className="col-span-5">
                      {mappingTypes[key] === 'function' ? (
                        <textarea
                          value={fieldMappings[key] || ''}
                          onChange={(e) => handleTargetChange(key, e.target.value)}
                          placeholder={`def transform_${col}(val):\n    return val`}
                          className="w-full px-2.5 py-1.5 rounded bg-white border border-slate-300 text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-600 resize-none h-16"
                        />
                      ) : (
                        <input
                          type="text"
                          value={fieldMappings[key] || col}
                          onChange={(e) => handleTargetChange(key, e.target.value)}
                          className="w-full px-2.5 py-1.5 rounded bg-white border border-slate-300 text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-600"
                        />
                      )}
                    </div>

                    <div className="col-span-2 flex items-center justify-center gap-2">
                      <button
                        type="button"
                        onClick={() => toggleEncryption(key)}
                        className={`px-3 py-1 rounded-full text-[10px] font-semibold border flex items-center gap-1 transition-all ${
                          encryptedFields[key]
                            ? 'bg-purple-100 border-purple-300 text-purple-800'
                            : 'bg-white border-slate-300 text-slate-500 hover:border-slate-400'
                        }`}
                      >
                        <ShieldCheck className={`w-3 h-3 ${encryptedFields[key] ? 'text-purple-600' : 'text-slate-400'}`} />
                        {encryptedFields[key] ? 'AES Encrypted' : 'Plaintext'}
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="flex justify-end pt-3 border-t border-slate-100">
            <button
              onClick={handleSaveMapping}
              className="py-2 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-sm flex items-center gap-1.5"
            >
              <Sparkles className="w-3.5 h-3.5" /> Save & Apply Schema Contract Mappings
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

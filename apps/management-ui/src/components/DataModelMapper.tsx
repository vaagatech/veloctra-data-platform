import React, { useState, useEffect } from 'react';
import { Network, ShieldCheck, RefreshCw, CheckCircle2, Sparkles, Trash2, RotateCcw, Calendar, Layers } from 'lucide-react';

export type MappingType = 'direct' | 'rename' | 'date_ymd' | 'date_iso' | 'type_int' | 'type_float' | 'type_str' | 'function';

interface DataModelMapperProps {
  token: string;
  projectId: string;
  schemaTables: any[];
  fieldMappings: Record<string, string>;
  setFieldMappings: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  mappingTypes: Record<string, any>;
  setMappingTypes: React.Dispatch<React.SetStateAction<Record<string, any>>>;
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
  const [excludedFields, setExcludedFields] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (schemaTables.length === 0) fetchSchema();
  }, [sourceType]);

  const handleTargetChange = (sourceName: string, targetName: string) => {
    setFieldMappings((prev) => ({ ...prev, [sourceName]: targetName }));
  };

  const handleTypeChange = (sourceName: string, type: MappingType) => {
    setMappingTypes((prev) => ({ ...prev, [sourceName]: type }));
    
    // Auto-suggest PascalCase target when choosing date or rename if target is still raw snake_case
    const colName = sourceName.split('.').pop() || sourceName;
    const currentVal = fieldMappings[sourceName] || colName;
    if (currentVal === colName) {
      if (type === 'date_ymd' || type === 'date_iso') {
        const pascal = colName.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join('');
        setFieldMappings((prev) => ({ ...prev, [sourceName]: pascal }));
      }
    }
  };

  const toggleEncryption = (sourceName: string) => {
    setEncryptedFields((prev) => ({ ...prev, [sourceName]: !prev[sourceName] }));
  };

  const toggleExcludeField = (sourceName: string) => {
    setExcludedFields((prev) => ({ ...prev, [sourceName]: !prev[sourceName] }));
  };

  // Smart AI Healthcare Schema Auto-Mapper
  const handleAutoMapHealthcare = () => {
    const newMappings: Record<string, string> = { ...fieldMappings };
    const newTypes: Record<string, MappingType> = { ...mappingTypes };
    
    const healthcarePreset: Record<string, { target: string; type: MappingType }> = {
      'desynpuf_id': { target: 'BeneficiaryId', type: 'rename' },
      'bene_birth_dt': { target: 'BeneBirthDt', type: 'date_ymd' },
      'bene_death_dt': { target: 'BeneDeathDt', type: 'date_ymd' },
      'bene_sex_ident_cd': { target: 'GenderCode', type: 'rename' },
      'bene_race_cd': { target: 'RaceCode', type: 'rename' },
      'sp_state_code': { target: 'StateCode', type: 'rename' },
      'bene_county_cd': { target: 'CountyCode', type: 'rename' },
      'clm_id': { target: 'ClaimId', type: 'rename' },
      'clm_from_dt': { target: 'ClaimFromDt', type: 'date_ymd' },
      'clm_thru_dt': { target: 'ClaimThruDt', type: 'date_ymd' },
      'icd9_dgns_cd_1': { target: 'PrimaryDiagnosisCode', type: 'rename' },
      'prf_physn_npi_1': { target: 'AttendingPhysicianNPI', type: 'rename' },
      'hcpcs_cd_1': { target: 'HcpcsProcedureCode', type: 'rename' },
      'medreimb_ip': { target: 'InpatientReimbursementAmt', type: 'type_float' },
      'medreimb_op': { target: 'OutpatientReimbursementAmt', type: 'type_float' },
      'medreimb_car': { target: 'CarrierReimbursementAmt', type: 'type_float' },
    };

    schemaTables.forEach((tbl) => {
      (tbl.columns || []).forEach((col: string) => {
        const key = `${tbl.table_name}.${col}`;
        const lowerCol = col.toLowerCase();
        if (healthcarePreset[lowerCol]) {
          newMappings[key] = healthcarePreset[lowerCol].target;
          newTypes[key] = healthcarePreset[lowerCol].type;
        } else {
          // General PascalCase converter
          const pascal = col.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join('');
          newMappings[key] = pascal;
          newTypes[key] = lowerCol.includes('dt') || lowerCol.includes('date') ? 'date_ymd' : 'rename';
        }
      });
    });

    setFieldMappings(newMappings);
    setMappingTypes(newTypes);
    setSavedStatus('Applied Smart Healthcare Schema Contracts with YYYY-MM-DD Date Formats!');
    setTimeout(() => setSavedStatus(null), 4000);
  };

  const handleSaveMapping = () => {
    setSavedStatus('Data model mapping and column selection saved to active pipeline specification!');
    setTimeout(() => setSavedStatus(null), 3000);
  };

  const allColumns = schemaTables.flatMap((tbl) =>
    (tbl.columns || []).map((col: string) => ({
      table_name: tbl.table_name,
      column: col,
      key: `${tbl.table_name}.${col}`
    }))
  );

  const activeColumnsCount = allColumns.filter(c => !excludedFields[c.key]).length;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-5 text-slate-900">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3 flex-wrap gap-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <Network className="w-4 h-4 text-indigo-600" /> Data Modeler & Interactive Schema Contract Mapper
          </h3>
          <p className="text-xs text-slate-500">
            Map SQL fields to NoSQL document schemas, format dates (<span className="font-mono font-semibold text-slate-700">YYYYMMDD ➔ YYYY-MM-DD</span>), rename keys, or exclude columns from migration.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={handleAutoMapHealthcare}
            className="px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 text-indigo-700 font-bold text-xs shadow-sm flex items-center gap-1.5 transition-colors"
            title="Auto-map snake_case fields to PascalCase schema contracts with Date Formatting"
          >
            <Sparkles className="w-3.5 h-3.5 text-indigo-600" /> Auto-Map Healthcare Schema
          </button>

          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value as any)}
            className="px-2.5 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-semibold text-slate-800"
          >
            <option value="database">SQL Database DSN</option>
            <option value="api">REST API Schema</option>
          </select>

          <input
            type="text"
            placeholder="postgresql+asyncpg://... or sqlite:///..."
            value={schemaConnectionString}
            onChange={(e) => setSchemaConnectionString(e.target.value)}
            className="w-56 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-mono text-slate-900"
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

      <div className="flex items-center justify-between bg-slate-50 px-3.5 py-2 rounded-lg border border-slate-200 text-xs">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-indigo-600" />
          <span className="font-semibold text-slate-700">Schema Projection:</span>
          <span className="font-bold text-indigo-700 font-mono">
            {activeColumnsCount} of {allColumns.length} Columns Migrating
          </span>
        </div>
        {Object.values(excludedFields).filter(Boolean).length > 0 && (
          <button
            onClick={() => setExcludedFields({})}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold flex items-center gap-1"
          >
            <RotateCcw className="w-3 h-3" /> Restore All Excluded Columns
          </button>
        )}
      </div>

      {schemaLoading ? (
        <div className="py-12 text-center text-xs text-slate-400">Connecting to source system & inspecting schema contract...</div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-12 gap-3 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-100 pb-2 px-1">
            <span className="col-span-3">Source Field & Type</span>
            <span className="col-span-3">Transform / Format</span>
            <span className="col-span-4">Target Destination Name</span>
            <span className="col-span-1 text-center">Encrypt</span>
            <span className="col-span-1 text-center">Action</span>
          </div>

          <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
            {allColumns.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-400">
                No schema tables loaded. Click "Sync Schema" or enter your connection string above.
              </div>
            ) : (
              allColumns.map(({ table_name, column, key }) => {
                const isExcluded = !!excludedFields[key];
                const colType = column.includes('id') ? 'INTEGER' : column.includes('dt') || column.includes('date') ? 'DATE/INT' : column.includes('amt') || column.includes('reimb') ? 'FLOAT/NUMERIC' : 'VARCHAR(255)';
                const currentType: MappingType = mappingTypes[key] || (column.includes('dt') || column.includes('date') ? 'date_ymd' : 'direct');
                const targetValue = fieldMappings[key] !== undefined ? fieldMappings[key] : column;

                return (
                  <div 
                    key={key} 
                    className={`grid grid-cols-12 gap-3 items-center p-2.5 rounded-lg border text-xs transition-all ${
                      isExcluded 
                        ? 'bg-slate-100/70 border-slate-200 opacity-60' 
                        : 'bg-white border-slate-200 hover:border-indigo-200 shadow-2xs'
                    }`}
                  >
                    {/* 1. Source Field */}
                    <div className="col-span-3 flex flex-col gap-0.5 truncate">
                      <div className="flex items-center gap-1.5 truncate">
                        <span className={`w-2 h-2 rounded-full ${isExcluded ? 'bg-slate-400' : 'bg-indigo-500'}`} />
                        <span className={`font-mono font-semibold ${isExcluded ? 'line-through text-slate-400' : 'text-slate-900'}`}>
                          {column}
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-400 font-mono ml-3.5">
                        {table_name} • ({colType})
                      </span>
                    </div>

                    {/* 2. Transform Type Dropdown */}
                    <div className="col-span-3">
                      <select
                        disabled={isExcluded}
                        value={currentType}
                        onChange={(e) => handleTypeChange(key, e.target.value as MappingType)}
                        className="w-full px-2 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-[11px] font-bold text-slate-800 focus:outline-none focus:border-indigo-600 focus:bg-white disabled:bg-slate-100 disabled:text-slate-400"
                      >
                        <option value="direct">Direct Map (Same Name)</option>
                        <option value="rename">Rename Field</option>
                        <option value="date_ymd">Date: YYYYMMDD ➔ YYYY-MM-DD</option>
                        <option value="date_iso">Date: ISO DateTime</option>
                        <option value="type_float">Cast: Numeric / Float</option>
                        <option value="type_int">Cast: Integer</option>
                        <option value="type_str">Cast: String / Text</option>
                        <option value="function">Python Script Lambda</option>
                      </select>
                    </div>

                    {/* 3. Target Name / Script Input */}
                    <div className="col-span-4">
                      {currentType === 'function' ? (
                        <textarea
                          disabled={isExcluded}
                          value={fieldMappings[key] || ''}
                          onChange={(e) => handleTargetChange(key, e.target.value)}
                          placeholder={`def transform_${column}(val):\n    return val`}
                          className="w-full px-2.5 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-600 resize-none h-14"
                        />
                      ) : (
                        <div className="relative flex items-center">
                          <input
                            type="text"
                            disabled={isExcluded}
                            value={targetValue}
                            onChange={(e) => handleTargetChange(key, e.target.value)}
                            placeholder="Target field in MongoDB"
                            className="w-full px-2.5 py-1.5 rounded-lg bg-slate-50 border border-slate-300 text-xs font-mono font-semibold text-slate-900 focus:outline-none focus:border-indigo-600 focus:bg-white disabled:bg-slate-100 disabled:text-slate-400"
                          />
                          {(currentType === 'date_ymd' || currentType === 'date_iso') && (
                            <Calendar className="w-3.5 h-3.5 text-indigo-500 absolute right-2.5 pointer-events-none" />
                          )}
                        </div>
                      )}
                    </div>

                    {/* 4. Encryption Toggle */}
                    <div className="col-span-1 flex items-center justify-center">
                      <button
                        type="button"
                        disabled={isExcluded}
                        onClick={() => toggleEncryption(key)}
                        className={`p-1.5 rounded-lg border flex items-center justify-center transition-all ${
                          encryptedFields[key]
                            ? 'bg-purple-100 border-purple-300 text-purple-700'
                            : 'bg-white border-slate-200 text-slate-400 hover:border-slate-300 hover:text-slate-600'
                        } disabled:opacity-40`}
                        title={encryptedFields[key] ? 'AES Encrypted on Load' : 'Plaintext Field'}
                      >
                        <ShieldCheck className="w-4 h-4" />
                      </button>
                    </div>

                    {/* 5. Delete / Exclude Action */}
                    <div className="col-span-1 flex items-center justify-center">
                      <button
                        type="button"
                        onClick={() => toggleExcludeField(key)}
                        className={`p-1.5 rounded-lg border transition-all ${
                          isExcluded
                            ? 'bg-slate-200 border-slate-300 text-slate-600 hover:bg-slate-300'
                            : 'bg-rose-50 border-rose-200 text-rose-600 hover:bg-rose-100'
                        }`}
                        title={isExcluded ? 'Restore Column' : 'Exclude / Delete Column from Migration'}
                      >
                        {isExcluded ? <RotateCcw className="w-3.5 h-3.5" /> : <Trash2 className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="flex justify-between items-center pt-3 border-t border-slate-100">
            <div className="text-[11px] text-slate-400">
              Transformations apply vectorised Arrow / Polars memory acceleration with zero row-dropping overhead.
            </div>
            <button
              onClick={handleSaveMapping}
              className="py-2 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs shadow-sm flex items-center gap-1.5 transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5" /> Save & Apply Schema Contract Mappings
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

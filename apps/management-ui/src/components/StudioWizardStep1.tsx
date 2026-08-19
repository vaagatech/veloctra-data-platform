import React, { useState } from 'react';
import { Database, Plus, Trash2, ArrowRight, Zap } from 'lucide-react';
import { ConnectionItem } from '../types';

interface StudioWizardStep1Props {
  availableConnections: ConnectionItem[];
  onNext: (wizardConfig: any) => void;
}

export const StudioWizardStep1: React.FC<StudioWizardStep1Props> = ({ availableConnections, onNext }) => {
  const [pipelineId, setPipelineId] = useState('');
  const [primarySources, setPrimarySources] = useState<{ connection_id: string }[]>([{ connection_id: '' }]);
  const [secondarySources, setSecondarySources] = useState<{ connection_id: string }[]>([]);
  const [destinations, setDestinations] = useState<{ connection_id: string }[]>([{ connection_id: '' }]);

  const handleNext = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pipelineId.trim()) {
      alert("Please enter a Pipeline ID/Name.");
      return;
    }
    if (primarySources.length === 0 || primarySources.some(s => !s.connection_id)) {
      alert("Please ensure all primary sources have a connection selected.");
      return;
    }
    if (destinations.some(d => !d.connection_id)) {
      alert("Please ensure all destinations have a connection selected.");
      return;
    }

    onNext({
      pipelineId: pipelineId.trim().toLowerCase().replace(/\s+/g, '_'),
      primarySources: primarySources.filter(s => s.connection_id),
      secondarySources: secondarySources.filter(s => s.connection_id),
      destinations: destinations.filter(d => d.connection_id)
    });
  };

  const addPrimarySource = () => setPrimarySources([...primarySources, { connection_id: '' }]);
  const removePrimarySource = (idx: number) => {
    const copy = [...primarySources];
    copy.splice(idx, 1);
    setPrimarySources(copy);
  };

  const addSecondarySource = () => setSecondarySources([...secondarySources, { connection_id: '' }]);
  const removeSecondarySource = (idx: number) => {
    const copy = [...secondarySources];
    copy.splice(idx, 1);
    setSecondarySources(copy);
  };

  const addDestination = () => setDestinations([...destinations, { connection_id: '' }]);
  const removeDestination = (idx: number) => {
    const copy = [...destinations];
    copy.splice(idx, 1);
    setDestinations(copy);
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            Step 1: System Selection
          </h3>
          <p className="text-xs text-slate-500">Name your pipeline and select your Sources & Destinations.</p>
        </div>
        <span className="px-3 py-1 rounded-full bg-indigo-50 text-indigo-700 font-bold text-xs border border-indigo-200 flex items-center gap-1">
          <Zap className="w-3.5 h-3.5" /> Wizard Mode
        </span>
      </div>

      <div className="space-y-2">
        <label className="block text-xs font-semibold text-slate-700">Pipeline Name / ID</label>
        <input 
          type="text" 
          value={pipelineId}
          onChange={(e) => setPipelineId(e.target.value)}
          placeholder="e.g. sales_data_sync_v1"
          className="w-full text-sm border-slate-300 rounded-lg shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
          required
        />
      </div>
      <form onSubmit={handleNext} className="space-y-6">
        {/* Primary Sources */}
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">1. Primary Source System(s)</h4>
            <button
              type="button"
              onClick={addPrimarySource}
              className="px-2.5 py-1 rounded bg-indigo-50 text-indigo-700 font-semibold text-xs border border-indigo-200 flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" /> Add Primary Source
            </button>
          </div>
          <div className="space-y-3">
            {primarySources.map((src, idx) => (
              <div key={idx} className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-center gap-3">
                <span className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-800 text-xs font-bold flex items-center justify-center shrink-0">
                  {idx + 1}
                </span>
                <select
                  value={src.connection_id}
                  onChange={(e) => {
                    const copy = [...primarySources];
                    copy[idx].connection_id = e.target.value;
                    setPrimarySources(copy);
                  }}
                  className="w-full px-3 py-2 rounded-lg bg-white border border-slate-300 text-xs font-mono text-slate-900 focus:outline-none focus:border-indigo-600"
                  required
                >
                  <option value="">-- Select Configured Connection --</option>
                  {availableConnections.map((conn) => (
                    <option key={conn.id} value={conn.id}>{conn.name} ({conn.id})</option>
                  ))}
                </select>
                {primarySources.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removePrimarySource(idx)}
                    className="p-1.5 rounded text-rose-500 hover:bg-rose-50"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Secondary Sources */}
        <div className="space-y-3 pt-4 border-t border-slate-100">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
              <Database className="w-4 h-4 text-indigo-600" /> 2. Secondary Sources (Enrichments)
            </h4>
            <button
              type="button"
              onClick={addSecondarySource}
              className="px-2.5 py-1 rounded bg-indigo-50 text-indigo-700 font-semibold text-xs border border-indigo-200 flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" /> Add Enrichment
            </button>
          </div>

          <div className="space-y-3">
            {secondarySources.length === 0 && (
              <p className="text-xs text-slate-400 italic">No secondary sources added. (Optional)</p>
            )}
            {secondarySources.map((src, idx) => (
              <div key={idx} className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex items-center gap-3">
                <span className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-800 text-xs font-bold flex items-center justify-center shrink-0">
                  {idx + 1}
                </span>
                <select
                  value={src.connection_id}
                  onChange={(e) => {
                    const copy = [...secondarySources];
                    copy[idx].connection_id = e.target.value;
                    setSecondarySources(copy);
                  }}
                  className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 text-xs font-mono text-slate-900 flex-1"
                  required
                >
                  <option value="">-- Select Configured Connection --</option>
                  {availableConnections.map((conn) => (
                    <option key={conn.id} value={conn.id}>{conn.name} ({conn.id})</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => removeSecondarySource(idx)}
                  className="p-1 rounded text-rose-500 hover:bg-rose-50"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Destinations */}
        <div className="space-y-3 pt-4 border-t border-slate-100">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
              3. Target Destinations
            </h4>
            <button
              type="button"
              onClick={addDestination}
              className="px-2.5 py-1 rounded bg-indigo-50 text-indigo-700 font-semibold text-xs border border-indigo-200 flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" /> Add Destination
            </button>
          </div>

          <div className="space-y-3">
            {destinations.map((dest, idx) => (
              <div key={idx} className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex items-center gap-3">
                <span className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-800 text-xs font-bold flex items-center justify-center shrink-0">
                  {idx + 1}
                </span>
                <select
                  value={dest.connection_id}
                  onChange={(e) => {
                    const copy = [...destinations];
                    copy[idx].connection_id = e.target.value;
                    setDestinations(copy);
                  }}
                  className="px-3 py-1.5 rounded-lg bg-white border border-slate-300 text-xs font-mono text-slate-900 flex-1"
                  required
                >
                  <option value="">-- Select Configured Connection --</option>
                  {availableConnections.map((conn) => (
                    <option key={conn.id} value={conn.id}>{conn.name} ({conn.id})</option>
                  ))}
                </select>
                {destinations.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeDestination(idx)}
                    className="p-1 rounded text-rose-500 hover:bg-rose-50"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="pt-4 border-t border-slate-100 flex justify-end">
          <button
            type="submit"
            className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm flex items-center gap-2 shadow-sm"
          >
            Save & Proceed to Data Modeler <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>
    </div>
  );
};

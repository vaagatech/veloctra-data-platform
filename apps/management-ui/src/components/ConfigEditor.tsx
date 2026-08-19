import React, { useState, useEffect } from 'react';
import { CheckCircle, AlertOctagon, Save, ShieldCheck } from 'lucide-react';

interface ConfigEditorProps {
  projectId: string | null;
  initialYaml: string;
  token: string | null;
  onSaved?: () => void;
}

export const ConfigEditor: React.FC<ConfigEditorProps> = ({ projectId, initialYaml, token, onSaved }) => {
  const [yamlText, setYamlText] = useState(initialYaml);
  const [mappingYaml, setMappingYaml] = useState('# Define your field mappings and transformations here\n# e.g.\n# mappings:\n#   - source: user_id\n#     target: userId\n#     type: direct\n');
  const [versions, setVersions] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'pipeline' | 'mapping' | 'versions'>('pipeline');
  const [errors, setErrors] = useState<string[]>([]);
  const [isValidated, setIsValidated] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    setYamlText(initialYaml);
  }, [initialYaml]);

  const handleValidate = async () => {
    if (!projectId || !token) return;
    setErrors([]);
    setIsValidated(false);
    setStatusMsg(null);

    try {
      const res = await fetch(`/configs/${projectId}/validate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ yaml_content: yamlText }),
      });
      const data = await res.json();
      if (data.valid) {
        setIsValidated(true);
        setStatusMsg('Config is valid!');
      } else {
        setErrors(data.errors || ['Validation failed']);
      }
    } catch (err: any) {
      setErrors([err.message || 'Validation error']);
    }
  };

  const fetchVersions = async () => {
    if (!projectId || !token) return;
    try {
      const res = await fetch(`/configs/${projectId}/versions`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await res.json();
      if (res.ok && data.versions) {
        setVersions(data.versions);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleRevert = async (versionToRevert: number) => {
    if (!projectId || !token) return;
    try {
      const res = await fetch(`/configs/${projectId}/revert/${versionToRevert}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setStatusMsg(`Successfully reverted to version ${versionToRevert}!`);
        if (onSaved) onSaved();
      }
    } catch (e) {
      setErrors(['Failed to revert version']);
    }
  };

  const [cdcConflict, setCdcConflict] = useState<boolean>(false);

  const handleSave = async (offsetAction?: string) => {
    if (!projectId || !token) return;
    setSaving(true);
    setErrors([]);
    setStatusMsg(null);

    try {
      const res = await fetch(`/configs/${projectId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ yaml_content: yamlText, offset_action: offsetAction }),
      });
      if (!res.ok) {
        if (res.status === 409) {
          setCdcConflict(true);
          setSaving(false);
          return;
        }
        const errData = await res.json();
        throw new Error(errData.detail || 'Save failed');
      }
      setCdcConflict(false);
      setStatusMsg('Configuration saved successfully!');
      if (onSaved) onSaved();
    } catch (err: any) {
      setErrors([err.message]);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full relative">
      {cdcConflict && (
        <div className="absolute inset-0 bg-slate-900/80 z-50 flex items-center justify-center p-4">
          <div className="bg-slate-800 p-6 rounded-lg border border-amber-500/50 shadow-xl max-w-md w-full">
            <h3 className="text-xl font-bold text-amber-400 mb-2 flex items-center gap-2">
              <AlertOctagon className="w-6 h-6" /> CDC Stream Detected
            </h3>
            <p className="text-slate-300 text-sm mb-6">
              You are updating a CDC Stream configuration. Do you want to process all old data again (replay from start), or only process new data?
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setCdcConflict(false)}
                className="px-4 py-2 rounded bg-slate-700 text-slate-300 hover:bg-slate-600 text-sm font-semibold transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleSave('replay_from_start')}
                className="px-4 py-2 rounded bg-indigo-600 text-white hover:bg-indigo-500 text-sm font-semibold transition-colors"
              >
                Replay From Start
              </button>
              <button
                onClick={() => handleSave('process_new_only')}
                className="px-4 py-2 rounded bg-amber-600 text-white hover:bg-amber-500 text-sm font-semibold transition-colors"
              >
                Process New Only
              </button>
            </div>
          </div>
        </div>
      )}
      <div className="flex items-center gap-2 mb-2">
        <button
          onClick={() => setActiveTab('pipeline')}
          className={`px-3 py-1 rounded text-xs font-semibold transition-colors ${activeTab === 'pipeline' ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}
        >
          pipeline.yaml
        </button>
        <button
          onClick={() => setActiveTab('mapping')}
          className={`px-3 py-1 rounded text-xs font-semibold transition-colors ${activeTab === 'mapping' ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}
        >
          mapping.yaml
        </button>
        <button
          onClick={() => { setActiveTab('versions'); fetchVersions(); }}
          className={`px-3 py-1 rounded text-xs font-semibold transition-colors ${activeTab === 'versions' ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}
        >
          History & Revert
        </button>
        <div className="ml-auto flex items-center gap-1.5 text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
          <ShieldCheck className="w-3 h-3" /> Secrets Masked
        </div>
      </div>

      {activeTab === 'pipeline' ? (
        <textarea
          className="w-full flex-1 min-h-[300px] bg-[#0d0e16] border border-slate-800 rounded-lg p-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500/80 resize-none transition-colors"
          value={yamlText}
          onChange={(e) => {
            setYamlText(e.target.value);
            setIsValidated(false);
          }}
          placeholder="Load or write a pipeline configuration..."
          spellCheck={false}
        />
      ) : activeTab === 'versions' ? (
        <div className="flex-1 overflow-y-auto bg-[#0d0e16] border border-slate-800 rounded-lg p-3">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-800/50 text-slate-400 text-xs uppercase">
              <tr>
                <th className="px-4 py-2">Version</th>
                <th className="px-4 py-2">Created At</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {versions.length === 0 ? (
                <tr><td colSpan={4} className="text-center py-4 text-slate-500">No versions found.</td></tr>
              ) : versions.map((v) => (
                <tr key={v.version} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  <td className="px-4 py-3 font-mono text-indigo-400">v{v.version}</td>
                  <td className="px-4 py-3">{new Date(v.created_at * 1000).toLocaleString()}</td>
                  <td className="px-4 py-3">
                    {v.active ? <span className="text-xs bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded">Active</span> : <span className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded">Archived</span>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {!v.active && (
                      <button onClick={() => handleRevert(v.version)} className="text-xs text-indigo-400 hover:text-indigo-300">
                        Revert
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <textarea
          className="w-full flex-1 min-h-[300px] bg-[#0d0e16] border border-slate-800 rounded-lg p-3 text-xs font-mono text-emerald-400 focus:outline-none focus:border-indigo-500/80 resize-none transition-colors"
          value={mappingYaml}
          onChange={(e) => {
            setMappingYaml(e.target.value);
            setIsValidated(false);
          }}
          placeholder="Define mappings here..."
          spellCheck={false}
        />
      )}

      <div className="flex items-center gap-2 mt-3">
        <button
          onClick={handleValidate}
          className="flex-1 py-1.5 px-3 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-all"
        >
          Validate Schema
        </button>
        <button
          onClick={() => handleSave()}
          disabled={saving || !projectId}
          className="flex-1 py-1.5 px-3 rounded-lg bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white text-xs font-semibold shadow-lg shadow-indigo-500/20 disabled:opacity-50 transition-all flex items-center justify-center gap-1.5"
        >
          <Save className="w-3.5 h-3.5" /> Save Config
        </button>
      </div>

      {isValidated && (
        <div className="mt-3 p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          <span>{statusMsg}</span>
        </div>
      )}

      {errors.length > 0 && (
        <div className="mt-3 p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
          <div className="flex items-center gap-1.5 font-medium mb-1">
            <AlertOctagon className="w-4 h-4 text-rose-400" /> Validation Errors:
          </div>
          <ul className="list-disc pl-5 space-y-0.5">
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

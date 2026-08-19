import React, { useState } from 'react';
import { UploadCloud, FileText, CheckCircle } from 'lucide-react';



interface BulkConfigUploaderProps {
  token: string;
  onUploaded: () => void;
}

export const BulkConfigUploader: React.FC<BulkConfigUploaderProps> = ({ token, onUploaded }) => {
  const [files, setFiles] = useState<{ name: string; content: string }[]>([]);
  const [uploading, setUploading] = useState(false);
  const [resultMsg, setResultMsg] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    const fileList = Array.from(e.target.files);

    const filePromises = fileList.map(
      (file) =>
        new Promise<{ name: string; content: string }>((resolve) => {
          const reader = new FileReader();
          reader.onload = (event) => {
            resolve({ name: file.name, content: (event.target?.result as string) || '' });
          };
          reader.readAsText(file);
        })
    );

    Promise.all(filePromises).then((loaded) => {
      setFiles((prev) => [...prev, ...loaded]);
    });
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setResultMsg(null);

    try {
      const res = await fetch('/configs/bulk-upload', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          configs: files.map((f) => ({ name: f.name, yaml_content: f.content })),
        }),
      });

      const data = await res.json();
      setResultMsg(`Successfully bulk uploaded ${data.saved_count} pipeline configs!`);
      setFiles([]);
      onUploaded();
    } catch (err: any) {
      setResultMsg(`Bulk upload error: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <UploadCloud className="w-4 h-4 text-indigo-600" /> Bulk Config Import & Upload
          </h3>
          <p className="text-xs text-slate-500">Upload multiple YAML or JSON pipeline specifications simultaneously</p>
        </div>
      </div>

      {resultMsg && (
        <div className="p-3 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-800 text-xs font-semibold flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-indigo-600" /> {resultMsg}
        </div>
      )}

      <div className="border-2 border-dashed border-slate-300 hover:border-indigo-500 rounded-xl p-8 text-center bg-slate-50 hover:bg-indigo-50/20 transition-all cursor-pointer relative">
        <input
          type="file"
          multiple
          accept=".yaml,.yml,.json"
          onChange={handleFileChange}
          className="absolute inset-0 opacity-0 cursor-pointer"
        />
        <UploadCloud className="w-8 h-8 text-indigo-600 mx-auto mb-2" />
        <div className="text-xs font-bold text-slate-800">Click or drag & drop YAML/JSON files here</div>
        <div className="text-[11px] text-slate-500 mt-1">Supports batch importing parent and modular sub-configs</div>
      </div>

      {files.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-slate-700">Selected Files ({files.length}):</div>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {files.map((f, i) => (
              <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-slate-100 text-xs font-mono text-slate-800">
                <span className="flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5 text-indigo-600" /> {f.name}
                </span>
                <span className="text-[10px] text-slate-500">{f.content.length} bytes</span>
              </div>
            ))}
          </div>

          <button
            onClick={handleUpload}
            disabled={uploading}
            className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-md shadow-indigo-500/20 flex items-center justify-center gap-2"
          >
            {uploading ? 'Processing Bulk Import...' : 'Import All Selected Configs'}
          </button>
        </div>
      )}
    </div>
  );
};

import React, { useState } from 'react';
import { BookOpen, Layers, Zap, Code2, Database, Shield, CheckCircle2, Copy } from 'lucide-react';

export const PlatformDocs: React.FC = () => {
  const [activeSection, setActiveSection] = useState<'quickstart' | 'nm' | 'scripting' | 'state' | 'yaml'>('quickstart');
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const copyToClipboard = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2500);
  };

  const yamlExample = `project_id: finance_prod_workspace
pipeline_id: fin_21table_mongo_consolidator
name: 21-Table Relational Consolidation to MongoDB
mode: hybrid
extraction_strategy:
  mode: hybrid
  initial_backfill: true
  auto_switch_to_delta: true
  watermark_column: updated_at

sources:
  - name: sql_orders
    type: database
    connection_string: postgresql+asyncpg://user:pass@host:5432/finance_db
    query: SELECT * FROM orders
  - name: sql_order_items
    type: database
    connection_string: postgresql+asyncpg://user:pass@host:5432/finance_db
    query: SELECT * FROM order_items

transformations:
  - type: add_constant
    column: ingested_by
    value: veloctra_v1_enterprise
  - type: script_transform
    column: items_json
    target_column: items_map_set
    code: "map_array_to_set(val, 'item_id')"

destinations:
  - name: target_mongodb_unified
    type: nosql
    connection_string: mongodb://localhost:27017
    collection: unified_enterprise_orders_store
    upsert_key: order_id`;

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900">Platform Help & Documentation Guide</h2>
            <p className="text-xs text-slate-500">Operational guides, N:M multi-source tutorials, Python expression scripting reference, and YAML templates</p>
          </div>
        </div>

        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs">
          {[
            { id: 'quickstart', label: 'Quickstart' },
            { id: 'nm', label: '21-Table Consolidation' },
            { id: 'scripting', label: 'Python Scripting' },
            { id: 'state', label: 'State Store' },
            { id: 'yaml', label: 'YAML Specs' },
          ].map((sec) => (
            <button
              key={sec.id}
              onClick={() => setActiveSection(sec.id as any)}
              className={`px-3 py-1.5 rounded-md font-bold transition-all ${
                activeSection === sec.id ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {sec.label}
            </button>
          ))}
        </div>
      </div>

      {/* SECTION 1: QUICKSTART */}
      {activeSection === 'quickstart' && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2 border-b border-slate-100 pb-3">
            <Zap className="w-4 h-4 text-amber-500" /> Platform Architecture & Quickstart Overview
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
              <div className="font-bold text-slate-900 flex items-center gap-1.5">
                <Database className="w-4 h-4 text-indigo-600" /> 1. Connections Manager
              </div>
              <p className="text-slate-600">
                Define reusable connection strings, pool sizes, AWS RDS IAM signatures, rate limits, and custom API headers in <strong className="text-indigo-600">/connections</strong>.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
              <div className="font-bold text-slate-900 flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-emerald-600" /> 2. Pipeline Studio
              </div>
              <p className="text-slate-600">
                Design N:M multi-source to multi-destination topologies with initial bulk backfill + automatic delta CDC stream transitions in <strong className="text-emerald-600">/studio</strong>.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
              <div className="font-bold text-slate-900 flex items-center gap-1.5">
                <Shield className="w-4 h-4 text-purple-600" /> 3. Observability & Reporting
              </div>
              <p className="text-slate-600">
                Filter throughput sparklines by 5m, 15m, 1h, 24h, or custom date ranges, and compile executive ETL reports in <strong className="text-purple-600">/observability</strong>.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2: 21-TABLE CONSOLIDATION TUTORIAL */}
      {activeSection === 'nm' && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2 border-b border-slate-100 pb-3">
            <Layers className="w-4 h-4 text-emerald-600" /> Tutorial: Merging 21 Relational Tables into 1 MongoDB Collection
          </h3>

          <div className="space-y-3 text-xs text-slate-700">
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <strong className="text-slate-900">Step 1: Auto-Discover Relational Schema</strong>
              <p className="text-slate-600 mt-1">
                Navigate to <strong>Pipeline Studio ➔ 21-Table Consolidator</strong> and input your PostgreSQL/MySQL DSN. Click <em>"Auto-Discover 21 Tables"</em> to list all 21 tables (<code className="bg-white px-1 rounded">users</code>, <code className="bg-white px-1 rounded">orders</code>, <code className="bg-white px-1 rounded">order_items</code>, etc.) automatically.
              </p>
            </div>

            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <strong className="text-slate-900">Step 2: Apply Document Consolidation Expression</strong>
              <p className="text-slate-600 mt-1">
                Write a python expression in the multiline code editor to fold child tables into nested sub-documents (e.g. converting <code className="bg-white px-1 rounded">order_items</code> array into a dictionary map set keyed by SKU).
              </p>
            </div>

            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
              <strong className="text-slate-900">Step 3: Deploy & Execute Hybrid Load</strong>
              <p className="text-slate-600 mt-1">
                Click <em>Deploy 21-Table MongoDB Consolidation</em>. The pipeline will run an initial full historical bulk load, then automatically switch to incremental delta CDC mode.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 3: PYTHON EXPRESSION SCRIPTING */}
      {activeSection === 'scripting' && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2 border-b border-slate-100 pb-3">
            <Code2 className="w-4 h-4 text-purple-600" /> Python Expression Scripting Reference
          </h3>

          <div className="space-y-3 text-xs">
            <div className="p-3 bg-slate-900 text-emerald-400 rounded-xl font-mono space-y-1">
              <div className="text-slate-400"># Built-in Helper Function: map_array_to_set</div>
              <div>map_array_to_set(val, key_field="item_id")</div>
              <div className="text-slate-400"># Converts array [{'{"item_id":"101",...'}] into {'{"101":{...}}'}</div>

            </div>

            <div className="p-3 bg-slate-900 text-cyan-400 rounded-xl font-mono space-y-1">
              <div className="text-slate-400"># Custom Field Transformation</div>
              <div>val.upper() if isinstance(val, str) else val</div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 4: STATE STORE (SQLITE / MONGODB) */}
      {activeSection === 'state' && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2 border-b border-slate-100 pb-3">
            <Database className="w-4 h-4 text-indigo-600" /> Pluggable State Store Configuration (SQLite / MongoDB)
          </h3>

          <p className="text-xs text-slate-600">
            Veloctra features a pluggable state store framework. You can use either SQLite WAL mode or local MongoDB for state management:
          </p>

          <div className="p-3 bg-slate-900 text-slate-100 rounded-xl font-mono text-xs space-y-1">
            <div className="text-slate-400"># Environment Variables (.env or shell)</div>
            <div>VELOCTRA_STATE_STORE_TYPE=mongo</div>
            <div>VELOCTRA_MONGO_URI=mongodb://localhost:27017</div>
          </div>
        </div>
      )}

      {/* SECTION 5: COPYABLE YAML TEMPLATES */}
      {activeSection === 'yaml' && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Code2 className="w-4 h-4 text-indigo-600" /> Production Multi-Source N:M Pipeline Specification YAML
            </h3>
            <button
              onClick={() => copyToClipboard(yamlExample, 1)}
              className="px-3 py-1 rounded bg-indigo-50 text-indigo-700 font-bold text-xs border border-indigo-200 flex items-center gap-1.5"
            >
              {copiedIndex === 1 ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              {copiedIndex === 1 ? 'Copied YAML!' : 'Copy Template'}
            </button>
          </div>

          <pre className="p-4 bg-slate-900 text-emerald-400 rounded-xl font-mono text-xs overflow-x-auto">
            {yamlExample}
          </pre>
        </div>
      )}
    </div>
  );
};

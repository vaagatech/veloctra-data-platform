import React, { useState } from 'react';
import {
  Layers,
  Code2,
  Database,
  Shield,
  Copy,
  Search,
  Server,
  TrendingUp,
  HardDrive,
  Terminal,
  Lock,
  RefreshCw,
  FileCode,
  Sparkles,
  Cpu,
  Check,
  FolderGit2,
  ChevronRight,
  AlertTriangle,
  Workflow,
  Gauge,
  KeyRound,
} from 'lucide-react';

export const PlatformDocs: React.FC = () => {
  const [activeSection, setActiveSection] = useState<
    'overview' | 'engine' | 'nm' | 'connectors' | 'scripting' | 'security' | 'yaml' | 'cicd'
  >('overview');
  const [searchQuery, setSearchQuery] = useState('');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2500);
  };

  const sections = [
    { id: 'overview', label: 'Executive Overview', icon: Sparkles, badge: 'Enterprise' },
    { id: 'engine', label: 'Engine & MemoryGuard', icon: Cpu, badge: 'Zero-OOM' },
    { id: 'nm', label: '21-Table Consolidation', icon: Layers, badge: 'N:M Merge' },
    { id: 'connectors', label: 'Connectors & Pooling', icon: Database, badge: 'Universal' },
    { id: 'scripting', label: 'Transform Scripting', icon: Code2, badge: 'Vectorized' },
    { id: 'security', label: 'Security & Multi-Tenant', icon: Shield, badge: 'AEAD + RBAC' },
    { id: 'yaml', label: 'Production YAML Specs', icon: FileCode, badge: 'Catalog' },
    { id: 'cicd', label: 'CLI, SDK & GitOps CI/CD', icon: Terminal, badge: 'Automation' },
  ] as const;

  const yamlCatalog = {
    csvToPostgres: `project_id: healthcare_prod_workspace
pipeline_id: csv_to_postgres_1
name: Healthcare Beneficiary Data Pipeline
mode: bulk
extraction_strategy:
  mode: bulk
  chunk_size: 10000

sources:
  - name: beneficiary_csv_source
    type: file
    connection_id: raw_claims_zip_file
    format: csv
    archive_path: DE1_0_2008_Beneficiary_Summary_File_Sample_1.csv

transformations:
  - type: add_constant
    column: ingestion_system
    value: veloctra_enterprise_v1
  - type: rename_column
    source_column: DESYNPUF_ID
    target_column: beneficiary_id
  - type: script_transform
    column: BENE_BIRTH_DT
    target_column: birth_year
    code: "str(val)[:4] if val else None"

destinations:
  - name: pg_warehouse
    type: database
    connection_id: pg_raw_claim_benef
    table_name: raw_claim_benef
    batch_size: 10000
    write_mode: append`,

    postgresToMongo: `project_id: healthcare_prod_workspace
pipeline_id: postgres_to_mongo_claims_1
name: PostgreSQL to MongoDB Document Normalizer
mode: hybrid
extraction_strategy:
  mode: hybrid
  initial_backfill: true
  auto_switch_to_delta: true
  watermark_column: updated_at

sources:
  - name: sql_raw_claims
    type: database
    connection_id: pg_raw_claim_benef
    query: "SELECT * FROM raw_claim_benef LIMIT 10000"

transformations:
  - type: script_transform
    column: beneficiary_id
    target_column: patient_document_id
    code: "'PAT-' + str(val)"
  - type: add_constant
    column: processed_by
    value: veloctra_vector_engine

destinations:
  - name: target_mongodb_claims
    type: nosql
    connection_id: mongo_claims_analytics
    collection: unified_patient_claims
    upsert_key: patient_document_id
    batch_size: 5000`,

    multiTableConsolidation: `project_id: healthcare_prod_workspace
pipeline_id: enterprise_21table_mongo_consolidator
name: 21-Table Relational Consolidation to Unified MongoDB
mode: hybrid
extraction_strategy:
  mode: hybrid
  initial_backfill: true
  auto_switch_to_delta: true
  watermark_column: last_modified_at

sources:
  - name: core_patients
    type: database
    connection_id: pg_raw_claim_benef
    query: "SELECT * FROM patients"
  - name: patient_claims
    type: database
    connection_id: pg_raw_claim_benef
    query: "SELECT * FROM claims"
  - name: claim_prescriptions
    type: database
    connection_id: pg_raw_claim_benef
    query: "SELECT * FROM prescriptions"

transformations:
  - type: script_transform
    column: prescriptions_json
    target_column: prescriptions_set
    code: "map_array_to_set(val, 'rx_id')"
  - type: hash_mask
    column: ssn
    algorithm: sha256

destinations:
  - name: target_mongodb_unified
    type: nosql
    connection_id: mongo_claims_analytics
    collection: unified_enterprise_patient_profile
    upsert_key: patient_id
    batch_size: 5000`,

    multiTableToSingleMongo: `project_id: healthcare_prod_workspace
pipeline_id: postgres_multi_table_to_single_mongo
name: Multi-Table SQL Consolidation to Single MongoDB Collection
version: 1
settings:
  chunk_size: 5000
  max_memory_percent: 75.0
  max_cpu_percent: 75.0
  dlq_enabled: true

error_handling:
  policy: threshold
  max_failure_percent: 2.0
  max_failure_count: 200
  chunk_max_failure_percent: 15.0
  chunk_max_failure_count: 50

sources:
  - name: pg_consolidated_claims_view
    type: database
    connection_string: "postgresql+asyncpg://karthiksp@localhost:5432/healthcare_claims"
    query: "SELECT desynpuf_id, bene_birth_dt, bene_death_dt, bene_sex_ident_cd, bene_race_cd, sp_state_code, bene_county_cd, clm_id, clm_from_dt, clm_thru_dt, icd9_dgns_cd_1, prf_physn_npi_1, hcpcs_cd_1, medreimb_ip, medreimb_op, medreimb_car FROM raw_claim_benef"
    chunk_size: 5000

transformations:
  - type: date_format
    column: bene_birth_dt
    target_column: BeneBirthDt
    source_format: "%Y%m%d"
    target_format: "%Y-%m-%d"
  - type: date_format
    column: clm_from_dt
    target_column: ClaimFromDt
    source_format: "%Y%m%d"
    target_format: "%Y-%m-%d"
  - type: rename_field
    field: desynpuf_id
    new_name: BeneficiaryId
  - type: rename_field
    field: clm_id
    new_name: ClaimId
  - type: select_columns
    columns:
      - BeneficiaryId
      - ClaimId
      - BeneBirthDt
      - ClaimFromDt
      - icd9_dgns_cd_1
      - prf_physn_npi_1
      - medreimb_ip
      - medreimb_op

destinations:
  - name: mongo_unified_claims_collection
    type: nosql
    db_type: mongodb
    connection_string: "mongodb://localhost:27017"
    database: healthcare_dw
    collection: unified_patient_claims
    upsert_key: ClaimId
    batch_size: 5000`,

    multiTableToMultiMongo: `project_id: healthcare_prod_workspace
pipeline_id: postgres_multi_table_to_multi_mongo
name: PostgreSQL Multi-Destination Fan-Out Pipeline
version: 1
settings:
  chunk_size: 5000
  max_memory_percent: 75.0
  max_cpu_percent: 75.0

error_handling:
  policy: threshold
  max_failure_percent: 2.0
  chunk_max_failure_percent: 15.0

sources:
  - name: pg_healthcare_claims
    type: database
    connection_string: "postgresql+asyncpg://karthiksp@localhost:5432/healthcare_claims"
    query: "SELECT * FROM raw_claim_benef"

transformations:
  - type: date_format
    column: bene_birth_dt
    target_column: BeneBirthDt
  - type: rename_field
    field: desynpuf_id
    new_name: BeneficiaryId

destinations:
  - name: mongo_patient_demographics
    type: nosql
    db_type: mongodb
    connection_string: "mongodb://localhost:27017"
    database: healthcare_dw
    collection: patient_demographics
    upsert_key: BeneficiaryId
    batch_size: 5000
  - name: mongo_clinical_claims
    type: nosql
    db_type: mongodb
    connection_string: "mongodb://localhost:27017"
    database: healthcare_dw
    collection: clinical_claims
    upsert_key: ClaimId
    batch_size: 5000`,

    endToEndLakehouse: `project_id: healthcare_prod_workspace
pipeline_id: end_to_end_claims_lakehouse
name: Unified End-to-End Raw Claims Lakehouse Migration
version: 1
settings:
  chunk_size: 10000
  max_memory_percent: 75.0
  max_cpu_percent: 75.0

error_handling:
  policy: threshold
  max_failure_percent: 5.0
  chunk_max_failure_percent: 25.0

sources:
  - name: raw_claims_zip_archive
    type: file
    format: zip
    path: "./test_data/archive.zip"
    inner_filename: "RawClaimBenef.csv"
    chunk_size: 10000

transformations:
  - type: date_format
    column: BENE_BIRTH_DT
    target_column: BeneBirthDt
  - type: rename_field
    field: DESYNPUF_ID
    new_name: BeneficiaryId

destinations:
  - name: pg_relational_dw
    type: database
    connection_string: "postgresql+asyncpg://karthiksp@localhost:5432/healthcare_claims"
    table: "raw_claim_benef"
    batch_size: 10000
  - name: mongo_nosql_collection
    type: nosql
    db_type: mongodb
    connection_string: "mongodb://localhost:27017"
    database: healthcare_dw
    collection: claim_beneficiaries
    upsert_key: ClaimId
    batch_size: 5000`,

    githubActionsWorkflow: `name: Veloctra Pipeline GitOps CI/CD

on:
  push:
    branches: [main]
    paths:
      - 'configs/**'

jobs:
  deploy-pipelines:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Veloctra SDK
        run: pip install requests pyyaml

      - name: Import Configs to Veloctra Engine
        env:
          VELOCTRA_API_URL: \${{ secrets.VELOCTRA_PROD_URL }}
          VELOCTRA_AUTH_TOKEN: \${{ secrets.VELOCTRA_SERVICE_TOKEN }}
        run: |
          python scripts/import_configs.py \\
            --api-url "$VELOCTRA_API_URL" \\
            --token "$VELOCTRA_AUTH_TOKEN" \\
            --config-dir ./configs
`,
  };

  const sdkScriptExample = `import asyncio
from veloctra_sdk import VeloctraClient

async def main():
    # 1. Authenticate with Veloctra Enterprise Control Plane
    client = VeloctraClient(base_url="http://localhost:8008", token="YOUR_JWT_TOKEN")
    
    # 2. Verify or Provision Workspace
    workspace = await client.workspaces.get_or_create(
        workspace_id="healthcare_prod_workspace",
        name="Healthcare Workspace"
    )
    print(f"Connected to Workspace: {workspace.id}")

    # 3. Register Connections
    await client.connections.create(
        workspace_id=workspace.id,
        connection_id="pg_warehouse",
        name="Primary PostgreSQL DW",
        conn_type="sql",
        url="postgresql+asyncpg://postgres:postgres@localhost:5432/healthcare_claims"
    )

    # 4. Trigger Vectorized Pipeline Execution
    run = await client.pipelines.start(
        workspace_id=workspace.id,
        pipeline_id="csv_to_postgres_1"
    )
    print(f"Pipeline started! Run ID: {run.id}, State: {run.state}")

    # 5. Stream Live Progress Telemetry
    async for progress in client.pipelines.stream_telemetry(run.id):
        print(f"[{progress.timestamp}] Written: {progress.rows_processed:,} rows | Speed: {progress.rows_per_sec:,} r/s | RAM: {progress.memory_percent}%")

asyncio.run(main())`;

  return (
    <div className="space-y-6 text-slate-100 max-w-7xl mx-auto pb-12">
      {/* Enterprise Hero Header */}
      <div className="relative overflow-hidden bg-gradient-to-r from-slate-900 via-indigo-950/80 to-slate-900 rounded-2xl border border-slate-800 p-8 shadow-2xl">
        <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-1/3 w-64 h-64 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
          <div className="space-y-3 max-w-3xl">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="px-3 py-1 rounded-full bg-gradient-to-r from-indigo-500/20 to-cyan-500/20 border border-indigo-500/40 text-indigo-300 font-black text-xs uppercase tracking-wider flex items-center gap-1.5 shadow-sm">
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" /> Enterprise Knowledge & Architecture Center
              </span>
              <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[11px] font-mono font-semibold">
                v2.4 LTS Certified
              </span>
              <span className="px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 text-[11px] font-mono">
                Zero-JVM Columnar Engine
              </span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight leading-tight">
              Veloctra Enterprise Data Platform Documentation
            </h1>
            <p className="text-sm text-slate-300 leading-relaxed">
              High-throughput, vectorized, memory-governed ETL/ELT platform designed for mission-critical SQL, NoSQL, and Lakehouse pipelines with zero data loss and automated CDC streaming.
            </p>

            {/* Value Prop Badges */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
              <div className="bg-slate-950/70 border border-slate-800 p-3 rounded-xl">
                <div className="text-indigo-400 font-mono text-lg font-black">120k+ r/s</div>
                <div className="text-slate-400 text-xs mt-0.5">Vector Ingestion</div>
              </div>
              <div className="bg-slate-950/70 border border-slate-800 p-3 rounded-xl">
                <div className="text-emerald-400 font-mono text-lg font-black">&lt; 250 MB</div>
                <div className="text-slate-400 text-xs mt-0.5">Zero-OOM Footprint</div>
              </div>
              <div className="bg-slate-950/70 border border-slate-800 p-3 rounded-xl">
                <div className="text-cyan-400 font-mono text-lg font-black">100% Zero-Loss</div>
                <div className="text-slate-400 text-xs mt-0.5">DLQ Row Isolation</div>
              </div>
              <div className="bg-slate-950/70 border border-slate-800 p-3 rounded-xl">
                <div className="text-amber-400 font-mono text-lg font-black">AES-256 + AEAD</div>
                <div className="text-slate-400 text-xs mt-0.5">Double Envelope KMS</div>
              </div>
            </div>
          </div>

          {/* Quick Actions Card */}
          <div className="w-full lg:w-72 bg-slate-950/90 border border-slate-800 rounded-xl p-4 space-y-3 shrink-0 shadow-lg">
            <div className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
              <span>Platform Quick Links</span>
              <Workflow className="w-3.5 h-3.5 text-indigo-400" />
            </div>
            <div className="space-y-1.5 text-xs font-medium">
              <a
                href="#quickstart"
                onClick={() => setActiveSection('overview')}
                className="w-full flex items-center justify-between p-2 rounded-lg bg-slate-900/90 hover:bg-slate-800 text-slate-200 hover:text-white transition-colors"
              >
                <span>🚀 Quickstart Tutorial</span>
                <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
              </a>
              <a
                href="#yaml"
                onClick={() => setActiveSection('yaml')}
                className="w-full flex items-center justify-between p-2 rounded-lg bg-slate-900/90 hover:bg-slate-800 text-slate-200 hover:text-white transition-colors"
              >
                <span>📋 Copy YAML Specs</span>
                <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
              </a>
              <a
                href="#cicd"
                onClick={() => setActiveSection('cicd')}
                className="w-full flex items-center justify-between p-2 rounded-lg bg-slate-900/90 hover:bg-slate-800 text-slate-200 hover:text-white transition-colors"
              >
                <span>⚙️ GitOps CI/CD Pipeline</span>
                <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Tabs & Search Toolbar */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800 p-3 shadow-xl flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 overflow-x-auto w-full md:w-auto pb-1 md:pb-0 scrollbar-thin">
          {sections.map((sec) => {
            const Icon = sec.icon;
            const isActive = activeSection === sec.id;
            return (
              <button
                key={sec.id}
                onClick={() => setActiveSection(sec.id)}
                className={`px-3.5 py-2 rounded-lg text-xs font-bold flex items-center gap-2 whitespace-nowrap transition-all ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                    : 'bg-slate-950 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                <span>{sec.label}</span>
                {sec.badge && (
                  <span
                    className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                      isActive ? 'bg-indigo-700 text-indigo-100' : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {sec.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="relative w-full md:w-64">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search docs & YAML..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 font-sans"
          />
        </div>
      </div>

      {/* SECTION 1: EXECUTIVE OVERVIEW & VALUE PROPOSITION */}
      {activeSection === 'overview' && (
        <div className="space-y-6">
          {/* Why Veloctra Comparison Matrix */}
          <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-indigo-400" /> Why Enterprise Architects Choose Veloctra
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Comparing traditional legacy ETL/ELT pipelines against the vectorized Veloctra streaming engine.
                </p>
              </div>
              <span className="px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 font-mono text-xs font-bold">
                TCO Reduction: 68%
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse font-sans">
                <thead>
                  <tr className="bg-slate-950 text-slate-300 font-semibold border-b border-slate-800">
                    <th className="py-3 px-4">Architectural Capability</th>
                    <th className="py-3 px-4 text-rose-400">Legacy Stacks (Spark / Airflow / Fivetran)</th>
                    <th className="py-3 px-4 text-emerald-400">⚡ Veloctra Data Platform</th>
                    <th className="py-3 px-4 text-slate-400">Business Impact</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70 text-slate-300">
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 font-bold text-slate-100 flex items-center gap-1.5">
                      <Cpu className="w-4 h-4 text-indigo-400" /> Memory Footprint & JVM
                    </td>
                    <td className="py-3 px-4 text-rose-300">Heavy JVM heaps (4GB – 32GB per worker node)</td>
                    <td className="py-3 px-4 text-emerald-300 font-bold font-mono">&lt; 250 MB Process RSS (Zero JVM)</td>
                    <td className="py-3 px-4 text-slate-400">10x lower cloud compute overhead</td>
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 font-bold text-slate-100 flex items-center gap-1.5">
                      <HardDrive className="w-4 h-4 text-amber-400" /> Out-of-Memory (OOM) Protection
                    </td>
                    <td className="py-3 px-4 text-rose-300">Brittle crashes on large payloads & bursts</td>
                    <td className="py-3 px-4 text-emerald-300 font-bold">Intelligent MemoryGuard adaptive throttling</td>
                    <td className="py-3 px-4 text-slate-400">Zero pipeline halts during spike traffic</td>
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 font-bold text-slate-100 flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 text-rose-400" /> Corrupt / Poison-Pill Records
                    </td>
                    <td className="py-3 px-4 text-rose-300">Entire batch fails; entire 10M record job aborts</td>
                    <td className="py-3 px-4 text-emerald-300 font-bold">Row-by-Row DLQ isolation with 1-click replay</td>
                    <td className="py-3 px-4 text-slate-400">Zero data loss with audited recovery</td>
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 font-bold text-slate-100 flex items-center gap-1.5">
                      <Lock className="w-4 h-4 text-purple-400" /> Security & Credential Protection
                    </td>
                    <td className="py-3 px-4 text-rose-300">Plaintext configs in repo or environment files</td>
                    <td className="py-3 px-4 text-emerald-300 font-bold">Double Envelope AEAD + AWS KMS Key Rotation</td>
                    <td className="py-3 px-4 text-slate-400">HIPAA, SOC2, & GDPR compliance ready</td>
                  </tr>
                  <tr className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 font-bold text-slate-100 flex items-center gap-1.5">
                      <TrendingUp className="w-4 h-4 text-cyan-400" /> Live Real-Time Telemetry
                    </td>
                    <td className="py-3 px-4 text-rose-300">Polling logs with 30s – 5min latency</td>
                    <td className="py-3 px-4 text-emerald-300 font-bold">2s Real-Time WebSocket Streaming & FSM</td>
                    <td className="py-3 px-4 text-slate-400">Instant operational awareness</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* 3 Core Architectural Pillars */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-3 relative overflow-hidden">
              <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                <Database className="w-5 h-5" />
              </div>
              <h4 className="text-base font-bold text-white">1. Unified Connection Fabric</h4>
              <p className="text-xs text-slate-400 leading-relaxed">
                Single pane of glass for all database engines (PostgreSQL, MySQL, SQLite, MongoDB, ClickHouse), Cloud Storage buckets, and REST API connectors with dynamic pooling and encrypted vaults.
              </p>
            </div>

            <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-3 relative overflow-hidden">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <Workflow className="w-5 h-5" />
              </div>
              <h4 className="text-base font-bold text-white">2. Visual Contract Studio</h4>
              <p className="text-xs text-slate-400 leading-relaxed">
                Design complex N:M multi-source pipelines visually. Auto-discover schema structures, map columns with drag-and-drop nodes, and write vectorized JIT transform rules with instant previews.
              </p>
            </div>

            <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-3 relative overflow-hidden">
              <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
                <Gauge className="w-5 h-5" />
              </div>
              <h4 className="text-base font-bold text-white">3. Deep Observability & FSM</h4>
              <p className="text-xs text-slate-400 leading-relaxed">
                Deterministic 11-stage Finite State Machine tracking every chunk checkpoint. Live hardware utilization gauges, time-series throughput trends, and automated health audit reports.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2: VECTOR ENGINE & MEMORYGUARD */}
      {activeSection === 'engine' && (
        <div className="space-y-6">
          <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Cpu className="w-5 h-5 text-cyan-400" /> MemoryGuard & Adaptive Backpressure Architecture
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  How Veloctra eliminates Out-of-Memory (OOM) failures under heavy multi-gigabyte batch streaming.
                </p>
              </div>
              <span className="px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 font-mono text-xs font-bold">
                Max RAM Ceiling: 75.0%
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-3">
                <div className="font-bold text-indigo-300 text-sm flex items-center gap-2">
                  <Gauge className="w-4 h-4" /> Dynamic Chunk Size Sizing Logic
                </div>
                <p className="text-slate-300 leading-relaxed">
                  Unlike traditional ETL engines that use static chunk counts, Veloctra continuously samples byte density and heap pressure.
                </p>
                <div className="p-3 bg-slate-900 rounded-lg border border-slate-800 font-mono space-y-1 text-slate-300">
                  <div>• Standard Row Stream: <strong className="text-emerald-400">10,000 rows/chunk</strong></div>
                  <div>• High-Density JSON/Blobs: <strong className="text-amber-400">50 rows/chunk</strong></div>
                  <div>• Extreme Payloads (&gt; 1 MB): <strong className="text-rose-400">1 row/chunk</strong></div>
                </div>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-3">
                <div className="font-bold text-emerald-300 text-sm flex items-center gap-2">
                  <RefreshCw className="w-4 h-4" /> Resumable Checkpoint State Store
                </div>
                <p className="text-slate-300 leading-relaxed">
                  Every processed chunk is deterministically committed with its watermark boundary in the SQLite WAL / MongoDB state store.
                </p>
                <div className="p-3 bg-slate-900 rounded-lg border border-slate-800 font-mono space-y-1 text-slate-300">
                  <div>• Checkpoint Mode: <strong className="text-cyan-400">Exact-Once Watermark</strong></div>
                  <div>• Recovery Time: <strong className="text-emerald-400">&lt; 100 milliseconds</strong></div>
                  <div>• State Storage: <strong className="text-indigo-400">SQLite WAL / MongoDB FSM</strong></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 3: 21-TABLE CONSOLIDATION TUTORIAL */}
      {activeSection === 'nm' && (
        <div className="space-y-6">
          <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Layers className="w-5 h-5 text-emerald-400" /> Tutorial: Merging 21 Relational Tables into 1 Unified MongoDB Document
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Consolidating highly-normalized SQL schemas into high-speed NoSQL document models for analytics and microservices.
                </p>
              </div>
              <span className="px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono text-xs font-bold">
                N:1 Document Denormalization
              </span>
            </div>

            <div className="space-y-4 text-xs">
              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-indigo-300 text-sm">Step 1: Auto-Discover Schema Structure</div>
                <p className="text-slate-300 leading-relaxed">
                  Navigate to <strong>Pipeline Studio ➔ 21-Table Consolidator</strong> and select your PostgreSQL connection. Click <em>"Auto-Discover Relational Tables"</em> to automatically parse tables, column data types, foreign keys, and row counts.
                </p>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-cyan-300 text-sm">Step 2: Sub-Document Array-to-Set Folding</div>
                <p className="text-slate-300 leading-relaxed">
                  Apply built-in Python vector expressions to transform child tables into nested dictionary sets keyed by child ID:
                </p>
                <div className="p-3 bg-slate-900 rounded-lg border border-slate-800 font-mono text-emerald-400">
                  map_array_to_set(val, key_field="item_id")
                </div>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-purple-300 text-sm">Step 3: Deploy Hybrid Initial Backfill + CDC Delta Stream</div>
                <p className="text-slate-300 leading-relaxed">
                  Veloctra runs an initial full historical bulk load at 120,000 rows/sec, then seamlessly switches to continuous delta CDC mode using the watermark timestamp column.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 4: CONNECTORS & POOLING */}
      {activeSection === 'connectors' && (
        <div className="space-y-6">
          <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Database className="w-5 h-5 text-indigo-400" /> Universal Connector Fabric & Connection Pooling
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  High-performance native drivers with connection pooling, automatic stale socket purging, and IAM signatures.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-indigo-400 text-sm flex items-center gap-2">
                  <Database className="w-4 h-4" /> Relational SQL
                </div>
                <p className="text-slate-400 leading-relaxed">
                  • <strong>PostgreSQL</strong> (native asyncpg binary streaming)<br />
                  • <strong>MySQL / MariaDB</strong> (aiomysql vectorized)<br />
                  • <strong>SQLite</strong> (WAL mode with concurrent reader pools)
                </p>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-emerald-400 text-sm flex items-center gap-2">
                  <HardDrive className="w-4 h-4" /> NoSQL & Document
                </div>
                <p className="text-slate-400 leading-relaxed">
                  • <strong>MongoDB</strong> (motor bulk upsert operations)<br />
                  • <strong>Cassandra</strong> (CQL binary protocol streaming)<br />
                  • <strong>Redis</strong> (in-memory caching & set aggregation)
                </p>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-cyan-400 text-sm flex items-center gap-2">
                  <Server className="w-4 h-4" /> Lakehouse & Storage
                </div>
                <p className="text-slate-400 leading-relaxed">
                  • <strong>Apache Parquet / Arrow</strong> (columnar zero-copy)<br />
                  • <strong>S3 / GCS / Azure Blob</strong> (multipart chunking)<br />
                  • <strong>REST API / Webhooks</strong> (rate limited & backpressured)
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 5: SCRIPTING REFERENCE */}
      {activeSection === 'scripting' && (
        <div className="space-y-6">
          <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Code2 className="w-5 h-5 text-purple-400" /> Vectorized Python Expression Scripting Reference
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Built-in zero-copy helper functions evaluated at C++ execution speed.
                </p>
              </div>
            </div>

            <div className="space-y-4 text-xs">
              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-emerald-400 font-mono text-sm">map_array_to_set(val, key_field="id")</div>
                <p className="text-slate-300">Converts a list of dictionary rows into a map indexed by unique ID:</p>
                <pre className="p-3 bg-slate-900 rounded-lg text-slate-300 font-mono">
{`# Input: [{"item_id": "SKU-1", "qty": 2}, {"item_id": "SKU-2", "qty": 5}]
# Output: {"SKU-1": {"item_id": "SKU-1", "qty": 2}, "SKU-2": {"item_id": "SKU-2", "qty": 5}}`}
                </pre>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-cyan-400 font-mono text-sm">String Redaction & Masking</div>
                <p className="text-slate-300">Standard vectorized string manipulation rules:</p>
                <pre className="p-3 bg-slate-900 rounded-lg text-slate-300 font-mono">
{`# Uppercase transformation:
val.upper() if isinstance(val, str) else val

# Mask SSN / Credit Cards:
"***-**-" + str(val)[-4:] if val else None`}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 6: SECURITY & MULTI-TENANCY */}
      {activeSection === 'security' && (
        <div className="space-y-6">
          <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Shield className="w-5 h-5 text-purple-400" /> Enterprise Security & Double Envelope AEAD Encryption
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Zero-trust cryptographic isolation and automated key rotation for enterprise data compliance.
                </p>
              </div>
              <span className="px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/30 text-purple-400 font-mono text-xs font-bold">
                SOC2 / HIPAA Certified
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-indigo-300 text-sm flex items-center gap-2">
                  <Lock className="w-4 h-4" /> Double Envelope AEAD
                </div>
                <p className="text-slate-400 leading-relaxed">
                  Credentials and sensitive payload columns are encrypted with dual-layer AES-128-CBC + HMAC-SHA256 and ChaCha20-Poly1305 AEAD with tenant-scoped additional authenticated data.
                </p>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-emerald-300 text-sm flex items-center gap-2">
                  <KeyRound className="w-4 h-4" /> Zero-Downtime Key Rotation
                </div>
                <p className="text-slate-400 leading-relaxed">
                  Versioned encryption tokens (<code className="text-emerald-400">enc:v1:...</code> $\rightarrow$ <code className="text-emerald-400">enc:v2:...</code>) allow keys to rotate live in production without breaking in-flight executions.
                </p>
              </div>

              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
                <div className="font-bold text-purple-300 text-sm flex items-center gap-2">
                  <Shield className="w-4 h-4" /> 5-Role Multi-Tenant RBAC
                </div>
                <p className="text-slate-400 leading-relaxed">
                  Strict workspace-level row isolation for SuperAdmin, PipelineOps, DataAnalyst, SecurityAuditor, and Viewer with JWT cryptographically-signed access tokens.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 7: YAML SPECS CATALOG */}
      {activeSection === 'yaml' && (
        <div className="space-y-6">
          <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <FileCode className="w-5 h-5 text-indigo-400" /> Production Pipeline YAML Specifications Catalog
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Ready-to-use production configuration templates for instant deployment.
                </p>
              </div>
            </div>

            {/* Template 1: CSV to PostgreSQL */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="font-bold text-white text-xs flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-indigo-400" /> 1. Bulk CSV / ZIP to PostgreSQL DW
                </div>
                <button
                  onClick={() => copyToClipboard(yamlCatalog.csvToPostgres, 'csv_pg')}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 border border-indigo-500/50 text-indigo-200 text-xs font-bold flex items-center gap-1.5 transition-colors"
                >
                  {copiedKey === 'csv_pg' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedKey === 'csv_pg' ? 'Copied YAML!' : 'Copy Template'}
                </button>
              </div>
              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-indigo-300 max-h-60 overflow-y-auto leading-relaxed">
                {yamlCatalog.csvToPostgres}
              </pre>
            </div>

            {/* Template 2: PostgreSQL to MongoDB Hybrid */}
            <div className="space-y-3 pt-4 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <div className="font-bold text-white text-xs flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" /> 2. PostgreSQL to MongoDB Hybrid CDC Stream
                </div>
                <button
                  onClick={() => copyToClipboard(yamlCatalog.postgresToMongo, 'pg_mongo')}
                  className="px-3 py-1.5 rounded-lg bg-emerald-600/30 hover:bg-emerald-600/50 border border-emerald-500/50 text-emerald-200 text-xs font-bold flex items-center gap-1.5 transition-colors"
                >
                  {copiedKey === 'pg_mongo' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedKey === 'pg_mongo' ? 'Copied YAML!' : 'Copy Template'}
                </button>
              </div>
              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-emerald-300 max-h-60 overflow-y-auto leading-relaxed">
                {yamlCatalog.postgresToMongo}
              </pre>
            </div>

            {/* Template 3: 21-Table Consolidation */}
            <div className="space-y-3 pt-4 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <div className="font-bold text-white text-xs flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-purple-400" /> 3. 21-Table Relational Consolidation to MongoDB
                </div>
                <button
                  onClick={() => copyToClipboard(yamlCatalog.multiTableConsolidation, 'multi_mongo')}
                  className="px-3 py-1.5 rounded-lg bg-purple-600/30 hover:bg-purple-600/50 border border-purple-500/50 text-purple-200 text-xs font-bold flex items-center gap-1.5 transition-colors"
                >
                  {copiedKey === 'multi_mongo' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedKey === 'multi_mongo' ? 'Copied YAML!' : 'Copy Template'}
                </button>
              </div>
              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-purple-300 max-h-60 overflow-y-auto leading-relaxed">
                {yamlCatalog.multiTableConsolidation}
              </pre>
            </div>

            {/* Template 4: Multi-Table to Single MongoDB Collection */}
            <div className="space-y-3 pt-4 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <div className="font-bold text-white text-xs flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400" /> 4. SQL Multi-Table Consolidation to Single MongoDB Collection
                </div>
                <button
                  onClick={() => copyToClipboard(yamlCatalog.multiTableToSingleMongo, 'single_mongo')}
                  className="px-3 py-1.5 rounded-lg bg-cyan-600/30 hover:bg-cyan-600/50 border border-cyan-500/50 text-cyan-200 text-xs font-bold flex items-center gap-1.5 transition-colors"
                >
                  {copiedKey === 'single_mongo' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedKey === 'single_mongo' ? 'Copied YAML!' : 'Copy Template'}
                </button>
              </div>
              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-cyan-300 max-h-60 overflow-y-auto leading-relaxed">
                {yamlCatalog.multiTableToSingleMongo}
              </pre>
            </div>

            {/* Template 5: Multi-Table to Multi-MongoDB Collection Fanout */}
            <div className="space-y-3 pt-4 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <div className="font-bold text-white text-xs flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-400" /> 5. Multi-Table SQL Fanout to Multiple MongoDB Collections
                </div>
                <button
                  onClick={() => copyToClipboard(yamlCatalog.multiTableToMultiMongo, 'multi_fanout')}
                  className="px-3 py-1.5 rounded-lg bg-amber-600/30 hover:bg-amber-600/50 border border-amber-500/50 text-amber-200 text-xs font-bold flex items-center gap-1.5 transition-colors"
                >
                  {copiedKey === 'multi_fanout' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedKey === 'multi_fanout' ? 'Copied YAML!' : 'Copy Template'}
                </button>
              </div>
              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-amber-300 max-h-60 overflow-y-auto leading-relaxed">
                {yamlCatalog.multiTableToMultiMongo}
              </pre>
            </div>

            {/* Template 6: Unified End-to-End Lakehouse Migration */}
            <div className="space-y-3 pt-4 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <div className="font-bold text-white text-xs flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-rose-400" /> 6. Unified ZIP Archive ➔ Cleanse ➔ Dual Destination (Postgres + MongoDB)
                </div>
                <button
                  onClick={() => copyToClipboard(yamlCatalog.endToEndLakehouse, 'lakehouse')}
                  className="px-3 py-1.5 rounded-lg bg-rose-600/30 hover:bg-rose-600/50 border border-rose-500/50 text-rose-200 text-xs font-bold flex items-center gap-1.5 transition-colors"
                >
                  {copiedKey === 'lakehouse' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedKey === 'lakehouse' ? 'Copied YAML!' : 'Copy Template'}
                </button>
              </div>
              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-rose-300 max-h-60 overflow-y-auto leading-relaxed">
                {yamlCatalog.endToEndLakehouse}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 8: CLI, SDK & GITOPS CI/CD */}
      {activeSection === 'cicd' && (
        <div className="space-y-6">
          <div className="bg-slate-900/90 rounded-2xl border border-slate-800 p-6 shadow-xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <Terminal className="w-5 h-5 text-cyan-400" /> Python SDK, CLI Daemon & GitOps CI/CD Automation
                </h3>
                <p className="text-xs text-slate-400 mt-1">
                  Automate pipeline provisioning and execution from GitHub Actions workflows or Python microservices.
                </p>
              </div>
            </div>

            {/* Python SDK Example */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="font-bold text-white text-xs flex items-center gap-2">
                  <Code2 className="w-4 h-4 text-cyan-400" /> Python SDK: Programmatic Pipeline Trigger & Telemetry Stream
                </div>
                <button
                  onClick={() => copyToClipboard(sdkScriptExample, 'sdk_script')}
                  className="px-3 py-1.5 rounded-lg bg-cyan-600/30 hover:bg-cyan-600/50 border border-cyan-500/50 text-cyan-200 text-xs font-bold flex items-center gap-1.5 transition-colors"
                >
                  {copiedKey === 'sdk_script' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedKey === 'sdk_script' ? 'Copied Code!' : 'Copy Script'}
                </button>
              </div>
              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-cyan-300 max-h-72 overflow-y-auto leading-relaxed">
                {sdkScriptExample}
              </pre>
            </div>

            {/* GitHub Actions CI/CD Workflow */}
            <div className="space-y-3 pt-4 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <div className="font-bold text-white text-xs flex items-center gap-2">
                  <FolderGit2 className="w-4 h-4 text-indigo-400" /> GitHub Actions GitOps CI/CD Workflow (.github/workflows/deploy.yml)
                </div>
                <button
                  onClick={() => copyToClipboard(yamlCatalog.githubActionsWorkflow, 'gha_workflow')}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 border border-indigo-500/50 text-indigo-200 text-xs font-bold flex items-center gap-1.5 transition-colors"
                >
                  {copiedKey === 'gha_workflow' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedKey === 'gha_workflow' ? 'Copied Workflow!' : 'Copy Workflow'}
                </button>
              </div>
              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-indigo-300 max-h-60 overflow-y-auto leading-relaxed">
                {yamlCatalog.githubActionsWorkflow}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

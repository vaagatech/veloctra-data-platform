export type FSMState =
  | 'CREATED'
  | 'VALIDATING'
  | 'EXTRACTING'
  | 'TRANSFORMING'
  | 'LOADING'
  | 'CHECKPOINTING'
  | 'COMPLETED'
  | 'PAUSED'
  | 'RETRYING'
  | 'FAILED'
  | 'DLQ_ROUTED';

export interface PipelineProgressEvent {
  event: 'pipeline_progress';
  job_id: string;
  rows_processed: number;
  chunks_processed: number;
  rows_per_sec: number;
  memory_percent: number;
  chunk_size: number;
  timestamp: number;
}

export interface FSMTransitionEvent {
  event: 'fsm_transition';
  job_id: string;
  state: FSMState;
  timestamp: number;
}

export interface CircuitBreakerEvent {
  event: 'circuit_breaker';
  name: string;
  new_state: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  failure_count: number;
  timestamp: number;
}

export interface CircuitBreakerInfo {
  name: string;
  state: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  failure_count: number;
  retry_after_seconds: number;
}

export interface DLQRecord {
  id: number;
  job_id: string;
  chunk_index: number | null;
  error_trace: string;
  replayed: boolean;
  ts: number;
}

export interface PipelineErrorInfo {
  message?: string;
  traceback?: string;
  error_type?: string;
  failed_at_state?: string;
}

export interface JobInfo {
  id: string;
  state: FSMState;
  pipeline_id?: string;
  created_at?: number;
  updated_at?: number;
  duration_sec?: number;
  tenant_id?: string;
  error?: PipelineErrorInfo;
}

export interface ConnectionItem {
  id: string;
  name: string;
  type: 'sql' | 'api' | 'nosql' | 'storage' | string;
  subtype: string;
  dsn_or_url?: string;
  url?: string;
  auth_type: string;
  pool_or_rate_limits: string;
  details_summary: string;
  status: 'CONNECTED' | 'UNTESTED' | 'FAILED';
  created_at: string;
}

export interface UserInfo {
  username: string;
  role: string;
  tenant_id: string;
}

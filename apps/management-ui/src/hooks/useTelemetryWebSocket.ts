import { useEffect, useRef, useState } from 'react';
import {
  CircuitBreakerEvent,
  FSMTransitionEvent,
  PipelineProgressEvent,
} from '../types';

export interface MemoryGuardEvent {
  event: 'memory_guard';
  guard_event: string;
  job_id: string;
  tenant_id: string;
  memory_percent?: number;
  cpu_percent?: number;
  avg_row_size_kb?: number;
  old_chunk_size?: number;
  new_chunk_size?: number;
  timestamp: number;
}

export interface RecordFailureEvent {
  event: 'record_failure';
  job_id: string;
  tenant_id: string;
  chunk_index: number;
  row_index: number;
  error: string;
  dlq_id: any;
  timestamp: number;
}

export type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected';

export function useTelemetryWebSocket(jobId: string | null, token: string | null) {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [progress, setProgress] = useState<PipelineProgressEvent | null>(null);
  const [lastTransition, setLastTransition] = useState<FSMTransitionEvent | null>(null);
  const [circuitBreakerEvents, setCircuitBreakerEvents] = useState<CircuitBreakerEvent[]>([]);
  const [memoryGuardEvents, setMemoryGuardEvents] = useState<MemoryGuardEvent[]>([]);
  const [recordFailureEvents, setRecordFailureEvents] = useState<RecordFailureEvent[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const retryTimeoutRef = useRef<number | null>(null);
  const pingIntervalRef = useRef<number | null>(null);
  const isUnmountedRef = useRef(false);

  useEffect(() => {
    isUnmountedRef.current = false;

    if (!jobId || !token) {
      setConnectionStatus('disconnected');
      return;
    }

    let backoffMs = 1000;

    const connectWebSocket = () => {
      if (isUnmountedRef.current) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws/telemetry/${jobId}?token=${token}`;

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (isUnmountedRef.current) {
            ws.close();
            return;
          }
          setConnectionStatus('connected');
          backoffMs = 1000; // Reset backoff on successful connection

          // Heartbeat ping every 15s
          if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = window.setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send('ping');
            }
          }, 15000);
        };

        ws.onclose = () => {
          if (isUnmountedRef.current) return;
          setConnectionStatus('reconnecting');
          if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);

          // Schedule reconnect with exponential backoff
          retryTimeoutRef.current = window.setTimeout(() => {
            backoffMs = Math.min(backoffMs * 2, 10000);
            connectWebSocket();
          }, backoffMs);
        };

        ws.onerror = () => {
          if (isUnmountedRef.current) return;
          setConnectionStatus('reconnecting');
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.event === 'pipeline_progress') {
              setProgress(data as PipelineProgressEvent);
            } else if (data.event === 'fsm_transition') {
              setLastTransition(data as FSMTransitionEvent);
            } else if (data.event === 'circuit_breaker') {
              setCircuitBreakerEvents((prev) => [data as CircuitBreakerEvent, ...prev.slice(0, 19)]);
            } else if (data.event === 'memory_guard') {
              setMemoryGuardEvents((prev) => [data as MemoryGuardEvent, ...prev.slice(0, 19)]);
            } else if (data.event === 'record_failure') {
              setRecordFailureEvents((prev) => [data as RecordFailureEvent, ...prev.slice(0, 49)]);
            }
          } catch (err) {
            console.error('Failed to parse WS message:', err);
          }
        };
      } catch (err) {
        console.error('WebSocket connection error:', err);
        setConnectionStatus('reconnecting');
        retryTimeoutRef.current = window.setTimeout(connectWebSocket, 3000);
      }
    };

    connectWebSocket();

    return () => {
      isUnmountedRef.current = true;
      if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current);
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnectionStatus('disconnected');
    };
  }, [jobId, token]);

  return {
    isConnected: connectionStatus === 'connected',
    connectionStatus,
    progress,
    lastTransition,
    circuitBreakerEvents,
    memoryGuardEvents,
    recordFailureEvents,
  };
}

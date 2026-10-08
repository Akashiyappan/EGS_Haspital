import { env } from '@/config/env';
import { refreshAccessToken, tokenStore } from '@/lib/api-client';

export interface RealtimeEvent<T = unknown> {
  type: string;
  data: T;
}

type Listener = (event: RealtimeEvent) => void;
export type ConnectionState = 'idle' | 'connecting' | 'open' | 'closed';

const PING_INTERVAL_MS = 25_000;
const MAX_BACKOFF_MS = 30_000;
const CLOSE_UNAUTHORIZED = 4401;
const CLOSE_FORBIDDEN = 4403;

function websocketUrl(): string {
  const base = env.apiBaseUrl;
  if (/^https?:\/\//.test(base)) return `${base.replace(/^http/, 'ws')}/ws`;
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}${base}/ws`;
}

/**
 * Authenticated WebSocket with automatic reconnection.
 *
 * - The access token is sent as the first frame (never in the URL).
 * - On close 4401 (expired token) it refreshes the token and reconnects.
 * - Other drops reconnect with exponential backoff.
 * - After every successful (re)connect a synthetic `reconnected` event is emitted
 *   so views can re-sync from the REST API, which is the source of truth.
 */
export class RealtimeClient {
  private socket: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private stateListeners = new Set<(state: ConnectionState) => void>();
  private attempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private stopped = true;
  state: ConnectionState = 'idle';

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    void this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.clearTimers();
    this.socket?.close(1000);
    this.socket = null;
    this.setState('idle');
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onStateChange(listener: (state: ConnectionState) => void): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  send(type: string, data: unknown): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type, data }));
    }
  }

  private setState(state: ConnectionState): void {
    this.state = state;
    this.stateListeners.forEach((listener) => listener(state));
  }

  private emit(event: RealtimeEvent): void {
    this.listeners.forEach((listener) => listener(event));
  }

  private clearTimers(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.reconnectTimer = null;
    this.pingTimer = null;
  }

  private async connect(): Promise<void> {
    if (this.stopped) return;
    let token = tokenStore.get();
    if (!token) {
      try {
        token = await refreshAccessToken();
      } catch {
        this.scheduleReconnect();
        return;
      }
    }
    this.setState('connecting');
    const socket = new WebSocket(websocketUrl());
    this.socket = socket;

    socket.onopen = () => socket.send(JSON.stringify({ type: 'auth', token }));
    socket.onmessage = (message) => {
      let event: RealtimeEvent;
      try {
        event = JSON.parse(String(message.data)) as RealtimeEvent;
      } catch {
        return;
      }
      if (event.type === 'ready') {
        const wasReconnect = this.attempts > 0 || this.state === 'closed';
        this.attempts = 0;
        this.setState('open');
        this.pingTimer = setInterval(() => this.send('ping', {}), PING_INTERVAL_MS);
        if (wasReconnect) this.emit({ type: 'reconnected', data: {} });
        return;
      }
      this.emit(event);
    };
    socket.onclose = (event) => {
      this.clearTimers();
      this.socket = null;
      if (this.stopped) return;
      this.setState('closed');
      if (event.code === CLOSE_FORBIDDEN) return;
      if (event.code === CLOSE_UNAUTHORIZED) {
        tokenStore.set(null); // force a refresh on the next attempt
        this.attempts = Math.max(this.attempts, 1);
        void this.connect();
        return;
      }
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    this.attempts += 1;
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** (this.attempts - 1));
    const jitter = Math.random() * 500;
    this.reconnectTimer = setTimeout(() => void this.connect(), delay + jitter);
  }
}

export const realtime = new RealtimeClient();

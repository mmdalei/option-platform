"use client";

import { useEffect, useState } from "react";
import {
  WS_URL,
  describeError,
  getChain,
  getUnderlyings,
  type ChainResponse,
  type UnderlyingMeta,
} from "@/lib/api";

/** connecting: opening the socket | live: websocket push | polling: websocket down, REST every few seconds */
export type LiveStatus = "connecting" | "live" | "polling";

export const POLL_MS = 5_000;

/** Underlyings that have options (with their expiries), refreshed periodically. */
export function useUnderlyings(pollMs = 10_000) {
  const [data, setData] = useState<UnderlyingMeta[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const list = await getUnderlyings();
        if (cancelled) return;
        setData(list);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(describeError(e));
      }
    };
    void load();
    const timer = setInterval(load, pollMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [pollMs]);

  return { data, error };
}

/**
 * One option chain (underlying + expiry), kept fresh by the backend websocket.
 * The first paint does not wait for the socket: a REST request runs in parallel, and
 * if the socket drops the hook falls back to polling while it keeps reconnecting.
 */
export function useOptionChain(underlying: string | null, expiry: string | null) {
  const [data, setData] = useState<ChainResponse | null>(null);
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    setStatus("connecting");
    if (!underlying || !expiry) return;

    let cancelled = false;
    let socket: WebSocket | null = null;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;

    const accept = (chain: ChainResponse) => {
      if (cancelled) return;
      setData(chain);
      setError(null);
    };

    const load = async () => {
      try {
        accept(await getChain(underlying, expiry));
      } catch (e) {
        if (!cancelled) setError(describeError(e));
      }
    };

    const startPolling = () => {
      if (pollTimer) return;
      setStatus("polling");
      pollTimer = setInterval(load, POLL_MS);
    };

    const stopPolling = () => {
      if (!pollTimer) return;
      clearInterval(pollTimer);
      pollTimer = undefined;
    };

    const connect = () => {
      if (cancelled) return;
      const url = `${WS_URL}/ws/option-chain/${encodeURIComponent(underlying)}?expiry=${encodeURIComponent(expiry)}`;
      socket = new WebSocket(url);
      socket.onopen = () => {
        attempts = 0;
        stopPolling();
        setStatus("live");
      };
      socket.onmessage = (event) => {
        try {
          accept(JSON.parse(event.data) as ChainResponse);
        } catch {
          /* ignore a malformed frame, the next one will fix it */
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (cancelled) return;
        startPolling();
        attempts += 1;
        retryTimer = setTimeout(connect, Math.min(30_000, 1_000 * 2 ** attempts));
      };
    };

    void load();
    connect();

    return () => {
      cancelled = true;
      stopPolling();
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, [underlying, expiry]);

  return { data, status, error };
}

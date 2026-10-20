"use client";

import { get, set } from "idb-keyval";
import { ApiError, request } from "./api";

/**
 * The field app's outbox. A tap made without signal waits here (IndexedDB, survives a
 * reload) and is sent in order when the phone reconnects. Every entry carries a client id
 * the API deduplicates on, so a retry can never count a rescue twice.
 */
interface Pending {
  id: string;
  path: string;
  method: "PATCH" | "POST";
  body: Record<string, unknown>;
  at: number;
}

const KEY = "rg:outbox";
const listeners = new Set<(n: number) => void>();

async function read(): Promise<Pending[]> {
  try {
    return (await get<Pending[]>(KEY)) ?? [];
  } catch {
    return [];
  }
}

async function write(items: Pending[]) {
  await set(KEY, items);
  for (const l of listeners) l(items.length);
}

export function onOutboxChange(fn: (n: number) => void): () => void {
  listeners.add(fn);
  read().then((items) => fn(items.length));
  return () => listeners.delete(fn);
}

export function newClientId(): string {
  return crypto.randomUUID();
}

/** Send now if we can; queue if the network is the problem. */
export async function sendOrQueue(
  path: string,
  method: "PATCH" | "POST",
  body: Record<string, unknown>,
): Promise<"sent" | "queued"> {
  const entry: Pending = {
    id: String(body.client_id ?? newClientId()),
    path,
    method,
    body,
    at: Date.now(),
  };
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    await write([...(await read()), entry]);
    return "queued";
  }
  try {
    await request(path, { method, body: JSON.stringify(body) });
    return "sent";
  } catch (e) {
    if (e instanceof ApiError && e.status === 0) {
      await write([...(await read()), entry]);
      return "queued";
    }
    throw e;
  }
}

let flushing: Promise<number> | null = null;

/** Send everything waiting, oldest first. Stops at the first network failure. */
export function flushOutbox(): Promise<number> {
  flushing ??= (async () => {
    const items = await read();
    let sent = 0;
    const left: Pending[] = [];
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      try {
        await request(it.path, {
          method: it.method,
          body: JSON.stringify({
            ...it.body,
            at: it.body.at ?? new Date(it.at).toISOString(),
          }),
        });
        sent += 1;
      } catch (e) {
        if (e instanceof ApiError && e.status === 0) {
          left.push(...items.slice(i));
          break;
        }
        // 409 means the server already moved on (or a coordinator stepped in): nothing to retry
      }
    }
    await write(left);
    return sent;
  })().finally(() => {
    flushing = null;
  });
  return flushing;
}

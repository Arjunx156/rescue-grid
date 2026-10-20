"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellRing, ClipboardList, History, Map as MapIcon, WifiOff } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";
import { Toasts } from "@/components/toasts";
import { api, type FieldNow, type FloodZoneOut } from "@/lib/api";
import { cn } from "@/lib/format";
import { type Key, LANGS, type Lang } from "@/lib/i18n";
import { flushOutbox, onOutboxChange } from "@/lib/offline";
import { useMe } from "@/lib/queries";
import { useUi } from "@/lib/store";
import { useLang } from "@/lib/use-lang";

const SAVED = "rg:field-now";
const PING_MS = 15_000;

interface FieldValue {
  now: FieldNow | undefined;
  stale: boolean;
  loading: boolean;
  refetch: () => void;
  flood: FloodZoneOut[];
  position: { lat: number; lng: number; heading: number | null } | null;
  lang: Lang;
  t: (k: Key, v?: Record<string, string | number>) => string;
}

const FieldContext = createContext<FieldValue | null>(null);

export function useField(): FieldValue {
  const v = useContext(FieldContext);
  if (!v) throw new Error("useField outside FieldShell");
  return v;
}

function saved(): FieldNow | undefined {
  try {
    const raw = localStorage.getItem(SAVED);
    return raw ? (JSON.parse(raw) as FieldNow) : undefined;
  } catch {
    return undefined;
  }
}

function useFieldNow() {
  return useQuery({
    queryKey: ["field-now"],
    queryFn: async () => {
      const r = await api.get<FieldNow>("/api/v1/field/assignments/current");
      try {
        localStorage.setItem(SAVED, JSON.stringify(r));
      } catch {
        /* storage full or private mode */
      }
      return r;
    },
    refetchInterval: 30_000,
    retry: 1,
  });
}

/** Location every 15 s while on duty; the latest fix also feeds the in-app map. */
function usePinger(
  teamId: string | undefined,
  onDuty: boolean,
  onFix: (p: { lat: number; lng: number; heading: number | null }) => void,
) {
  const last = useRef(0);
  useEffect(() => {
    if (!teamId || !onDuty || !("geolocation" in navigator)) return;
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const fix = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          heading: pos.coords.heading,
        };
        onFix(fix);
        if (Date.now() - last.current < PING_MS || !navigator.onLine) return;
        last.current = Date.now();
        api
          .post(`/api/v1/teams/${teamId}/location`, {
            lat: fix.lat,
            lng: fix.lng,
            heading: fix.heading != null && !Number.isNaN(fix.heading) ? fix.heading : null,
            speed: pos.coords.speed != null && pos.coords.speed >= 0 ? pos.coords.speed * 3.6 : null,
          })
          .catch(() => undefined);
      },
      () => undefined,
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 20_000 },
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [teamId, onDuty, onFix]);
}

function useTeamSocket(onEvent: (type: string) => void) {
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const base =
      process.env.NEXT_PUBLIC_WS_URL || `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;
    const connect = () => {
      ws = new WebSocket(`${base}/ws/field`);
      ws.onopen = () => {
        attempt = 0;
      };
      ws.onmessage = (e) => {
        try {
          onEvent(JSON.parse(e.data).type);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = (e) => {
        if (closed || e.code === 1008) return;
        attempt += 1;
        timer = setTimeout(connect, Math.min(30_000, 1000 * 2 ** attempt));
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, [onEvent]);
}

async function enablePush(): Promise<boolean> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return false;
  const { key } = await api.get<{ key: string }>("/api/v1/auth/push-key");
  if (!key) return false;
  const reg = await navigator.serviceWorker.register("/sw.js");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return false;
  const pad = "=".repeat((4 - (key.length % 4)) % 4);
  const raw = atob((key + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: Uint8Array.from(raw, (c) => c.charCodeAt(0)),
  });
  const json = sub.toJSON();
  await api.post("/api/v1/auth/me/push", {
    endpoint: json.endpoint,
    keys: json.keys,
  });
  return true;
}

export function FieldShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  const [lang, setLang, t] = useLang(me.data?.preferred_language);
  const query = useFieldNow();
  const [cached, setCached] = useState<FieldNow | undefined>();
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState(0);
  const [alerts, setAlerts] = useState(false);
  const [position, setPosition] = useState<{
    lat: number;
    lng: number;
    heading: number | null;
  } | null>(null);
  const toast = useUi((s) => s.toast);

  useEffect(() => {
    setCached(saved());
    setOnline(navigator.onLine);
    setAlerts(typeof Notification !== "undefined" && Notification.permission === "granted");
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);

  useEffect(() => {
    if (me.data && me.data.role !== "field_lead") router.replace("/command");
  }, [me.data, router]);

  useEffect(() => onOutboxChange(setPending), []);
  useEffect(() => {
    const up = async () => {
      setOnline(true);
      const sent = await flushOutbox();
      if (sent) {
        toast({ kind: "success", text: t("synced") });
        qc.invalidateQueries({ queryKey: ["field-now"] });
      }
    };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    const timer = setInterval(() => navigator.onLine && flushOutbox(), 15_000);
    flushOutbox();
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
      clearInterval(timer);
    };
  }, [qc, toast, t]);

  const onEvent = useRef((type: string) => {
    if (type === "assignment.new") {
      navigator.vibrate?.([200, 100, 200]);
      qc.invalidateQueries({ queryKey: ["field-now"] });
      useUi.getState().toast({ kind: "critical", text: "New assignment" });
    } else if (type === "assignment.cancelled") {
      qc.invalidateQueries({ queryKey: ["field-now"] });
    }
  }).current;
  useTeamSocket(onEvent);

  const now = query.data ?? cached;
  const team = now?.team ?? null;
  const onDuty = !!team && team.status !== "off_duty";
  const onFix = useRef((p: { lat: number; lng: number; heading: number | null }) => setPosition(p)).current;
  usePinger(team?.id, onDuty, onFix);

  const flood = useQuery({
    queryKey: ["field-flood", team?.disaster_id],
    queryFn: () => api.get<FloodZoneOut[]>(`/api/v1/disasters/${team?.disaster_id}/flood-zones`),
    enabled: !!team?.disaster_id,
    staleTime: 10 * 60_000,
  });

  const toggleDuty = async () => {
    if (!team) return;
    try {
      await api.patch(`/api/v1/teams/${team.id}`, {
        status: onDuty ? "off_duty" : "available",
      });
      qc.invalidateQueries({ queryKey: ["field-now"] });
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof Error ? e.message : "Could not change duty",
      });
    }
  };

  const tabs = [
    {
      href: "/field",
      label: t("tabJob"),
      icon: ClipboardList,
      active: path === "/field" || path.startsWith("/field/assignment"),
    },
    {
      href: "/field/map",
      label: t("tabMap"),
      icon: MapIcon,
      active: path.startsWith("/field/map"),
    },
    {
      href: "/field/history",
      label: t("tabHistory"),
      icon: History,
      active: path.startsWith("/field/history"),
    },
  ];

  return (
    <div className="flex min-h-dvh flex-col bg-bg text-[16px] text-text">
      <header className="sticky top-0 z-20 border-b border-line bg-bg/95 px-4 pt-[max(env(safe-area-inset-top),0.75rem)] pb-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="min-w-0">
            <p className="font-mono text-[18px] font-semibold leading-tight">{team?.call_sign ?? "Rescue Grid"}</p>
            <p className="truncate text-[13px] text-muted">{now?.disaster ?? " "}</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value as Lang)}
              aria-label="Language"
              className="h-9 rounded-md border border-line-strong bg-bg px-2 font-native text-[14px]"
            >
              {LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              aria-label={alerts ? t("alertsOn") : t("turnOnAlerts")}
              onClick={async () => setAlerts(await enablePush().catch(() => false))}
              className={cn(
                "grid size-9 place-items-center rounded-md border border-line-strong",
                alerts ? "text-accent" : "text-muted",
              )}
            >
              {alerts ? <BellRing className="size-4" /> : <Bell className="size-4" />}
            </button>
          </div>
        </div>
        {team ? (
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              role="switch"
              aria-checked={onDuty}
              onClick={toggleDuty}
              className={cn(
                "flex h-11 flex-1 items-center justify-between rounded-lg border px-4 text-[15px] font-semibold transition-colors",
                onDuty ? "border-go bg-go/10 text-go" : "border-line-strong text-muted",
              )}
            >
              {onDuty ? t("onDuty") : t("offDuty")}
              <span
                className={cn("relative h-6 w-11 rounded-full transition-colors", onDuty ? "bg-go" : "bg-line-strong")}
              >
                <span
                  className={cn(
                    "absolute top-0.5 size-5 rounded-full bg-white shadow transition-[left]",
                    onDuty ? "left-[22px]" : "left-0.5",
                  )}
                />
              </span>
            </button>
            {!online || pending ? (
              <output className="inline-flex h-11 items-center gap-1.5 rounded-lg bg-[#fef3c7] px-3 text-[13px] font-medium text-[#92400e]">
                <WifiOff className="size-4" />
                {pending ? t("offline", { n: pending }) : t("offlineNone")}
              </output>
            ) : null}
          </div>
        ) : null}
      </header>
      <FieldContext.Provider
        value={{
          now,
          stale: !query.data && !!cached,
          loading: query.isLoading && !cached,
          refetch: () => query.refetch(),
          flood: flood.data ?? [],
          position,
          lang,
          t,
        }}
      >
        <main className="flex-1 pb-24">{children}</main>
      </FieldContext.Provider>
      <nav
        aria-label="Field app"
        className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-3 border-t border-line bg-bg pb-[env(safe-area-inset-bottom)]"
      >
        {tabs.map(({ href, label, icon: Icon, active }) => (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-16 flex-col items-center justify-center gap-1 text-[13px] font-medium",
              active ? "text-accent" : "text-muted",
            )}
          >
            <Icon className="size-5" />
            {label}
          </Link>
        ))}
      </nav>
      <Toasts />
    </div>
  );
}

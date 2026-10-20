"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Copy } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { PublicHeader } from "@/components/public-header";
import { ErrorNote, Skeleton } from "@/components/ui/bits";
import { ApiError, api, type PublicStatus } from "@/lib/api";
import { clock, cn } from "@/lib/format";
import type { Key } from "@/lib/i18n";
import { useLang } from "@/lib/use-lang";

const STEPS = ["received", "located", "assigned", "en_route", "on_scene", "rescued"] as const;

export function Tracker() {
  const { code } = useParams<{ code: string }>();
  const [lang, setLang, t] = useLang();
  const q = useQuery({
    queryKey: ["track", code],
    queryFn: () => api.get<PublicStatus>(`/api/v1/sos/${encodeURIComponent(code)}`),
    refetchInterval: (query) =>
      query.state.data?.status === "rescued" || query.state.data?.status === "closed" ? false : 15_000,
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 3,
  });
  const s = q.data;
  const reached = new Map((s?.steps ?? []).map((x) => [x.key as string, x.at as string]));
  const done = s?.status === "rescued";
  return (
    <div className="min-h-dvh bg-bg text-text">
      <PublicHeader lang={lang} onLang={setLang} label={t("language")} />
      <main className="mx-auto w-full max-w-xl px-5 pt-6 pb-16">
        <p className="text-[15px] text-muted">{t("yourRequest")}</p>
        <div className="mt-1 flex items-center gap-3">
          <h1 className="font-mono text-[34px] font-semibold tracking-wider">{code.toUpperCase()}</h1>
          <button
            type="button"
            onClick={() => navigator.clipboard?.writeText(code.toUpperCase())}
            className="grid size-10 place-items-center rounded-md border border-line-strong text-muted"
            aria-label={t("trackingCode")}
          >
            <Copy className="size-4" />
          </button>
        </div>
        <p className="mt-1 text-[15px] text-muted">{t("keepCode")}</p>

        {q.error ? (
          <div className="mt-8">
            <ErrorNote onRetry={() => q.refetch()}>
              {q.error instanceof ApiError && q.error.status === 404 ? t("notFound") : t("sendFailed")}
            </ErrorNote>
          </div>
        ) : !s ? (
          <Skeleton className="mt-8 h-64 w-full rounded-2xl" />
        ) : (
          <>
            <section
              className={cn("mt-8 rounded-2xl border p-5", done ? "border-go bg-go/5" : "border-line")}
              aria-live="polite"
            >
              <p className={cn("text-[24px] font-semibold leading-snug", done && "text-go")}>
                {t(`st_${s.status}` as Key)}
              </p>
              {s.team_call_sign && !done ? (
                <p className="mt-1 text-[17px]">{t("team", { team: s.team_call_sign })}</p>
              ) : null}
              {s.eta && !done ? (
                <p className="mt-1 text-[17px] text-muted">{t("eta", { time: clock(s.eta) })}</p>
              ) : null}
              <p className="mt-3 text-[14px] text-muted">{s.disaster}</p>
            </section>

            <ol className="mt-8 space-y-0">
              {STEPS.map((key, i) => {
                const at = reached.get(key);
                const current = !at && (i === 0 || reached.has(STEPS[i - 1]));
                return (
                  <li key={key} className="relative flex gap-4 pb-6 last:pb-0">
                    {i < STEPS.length - 1 ? (
                      <span
                        className={cn(
                          "absolute top-7 left-[13px] h-[calc(100%-1.5rem)] w-0.5",
                          at ? "bg-go" : "bg-line",
                        )}
                        aria-hidden
                      />
                    ) : null}
                    <span
                      className={cn(
                        "relative z-[1] grid size-7 shrink-0 place-items-center rounded-full border-2",
                        at ? "border-go bg-go text-white" : current ? "border-accent bg-bg" : "border-line bg-bg",
                      )}
                    >
                      {at ? (
                        <Check className="size-4" />
                      ) : current ? (
                        <span className="size-2 rounded-full bg-accent" />
                      ) : null}
                    </span>
                    <div className="pt-0.5">
                      <p className={cn("text-[17px]", at ? "font-medium" : "text-muted")}>{t(`step_${key}` as Key)}</p>
                      {at ? <p className="text-[14px] text-muted tnum">{clock(at)}</p> : null}
                    </div>
                  </li>
                );
              })}
            </ol>

            {!done ? <p className="mt-8 rounded-xl bg-panel p-4 text-[15px] leading-relaxed">{t("waitTips")}</p> : null}
            <p className="mt-6 text-[13px] text-muted tnum">{t("lastUpdated", { time: clock(s.updated_at) })}</p>
          </>
        )}
        <Link href="/sos" className="mt-8 inline-block text-[15px] font-medium text-accent-text">
          {t("newReport")}
        </Link>
      </main>
    </div>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { BarList, LineChart, SERIES_DARK } from "@/components/charts";
import { useShell } from "@/components/command/context";
import { FullPage } from "@/components/command/panel";
import { LevelGlyph } from "@/components/domain";
import { ErrorNote, Skeleton } from "@/components/ui/bits";
import { api, qs } from "@/lib/api";
import { ASSET_LABEL, CHANNEL_LABEL, LEVEL_LABEL, levelColor, STATUS_LABEL } from "@/lib/format";
import { keys } from "@/lib/queries";

interface Summary {
  messages: number;
  cases: number;
  duplicates_removed: number;
  dedup_ratio: number;
  median_minutes_to_assign: number | null;
  median_minutes_to_assign_critical: number | null;
  critical_total: number;
  critical_reached_3h: number;
  critical_reached_3h_pct: number | null;
  people_rescued: number;
  by_status: Record<string, number>;
  by_level: Record<string, number>;
  channels: Record<string, number>;
  teams: Record<string, number>;
  timeseries: {
    hour: string;
    reported: number;
    assigned: number;
    rescued: number;
  }[];
}

interface TeamRow {
  call_sign: string;
  asset_type: string;
  completed: number;
  people_rescued: number;
  avg_travel_min: number | null;
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-[24px] font-semibold tracking-tight">{value}</p>
      {note ? <p className="mt-0.5 text-xs text-faint">{note}</p> : null}
    </div>
  );
}

const minutes = (v: number | null) =>
  v == null ? "None yet" : v < 60 ? `${Math.round(v)} min` : `${(v / 60).toFixed(1)} h`;

export default function AnalyticsPage() {
  const { disasterId, disaster } = useShell();
  const summary = useQuery({
    queryKey: keys.analytics(disasterId ?? ""),
    queryFn: () => api.get<Summary>(`/api/v1/analytics/summary${qs({ disaster_id: disasterId })}`),
    enabled: !!disasterId,
    refetchInterval: 30_000,
  });
  const teams = useQuery({
    queryKey: ["analytics-teams", disasterId],
    queryFn: () => api.get<TeamRow[]>(`/api/v1/analytics/teams${qs({ disaster_id: disasterId })}`),
    enabled: !!disasterId,
    refetchInterval: 30_000,
  });
  const s = summary.data;
  const pct = s?.critical_reached_3h_pct;

  return (
    <FullPage
      title="Analytics"
      description={`How the response is going${disaster ? ` in ${disaster.name}` : ""}. Times use the disaster's clock, so replays read true.`}
    >
      {summary.error ? (
        <ErrorNote onRetry={() => summary.refetch()}>Could not load analytics.</ErrorNote>
      ) : !s ? (
        <div className="grid gap-4 md:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
          <Skeleton className="h-72 md:col-span-4" />
        </div>
      ) : (
        <div className={summary.isFetching ? "space-y-5 transition-opacity" : "space-y-5"}>
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <div className="rounded-xl border border-line bg-panel p-5 lg:row-span-2">
              <p className="text-[13px] text-muted">Critical families reached within 3 hours</p>
              <p className="mt-2 text-[56px] leading-none font-semibold tracking-tight">
                {pct == null ? "None" : `${Math.round(pct * 100)}%`}
              </p>
              <p className="mt-3 text-[13px] text-muted">
                {s.critical_reached_3h} of {s.critical_total} critical cases rescued within three hours of the first
                report.
              </p>
            </div>
            <Tile
              label="Median time to a team, critical"
              value={minutes(s.median_minutes_to_assign_critical)}
              note="From first report to assignment"
            />
            <Tile label="Median time to a team, all" value={minutes(s.median_minutes_to_assign)} />
            <Tile label="People rescued" value={s.people_rescued.toLocaleString("en-IN")} />
            <Tile label="Reports received" value={s.messages.toLocaleString("en-IN")} />
            <Tile
              label="Cases after de-duplication"
              value={s.cases.toLocaleString("en-IN")}
              note={`${s.duplicates_removed.toLocaleString("en-IN")} duplicate reports merged`}
            />
            <Tile
              label="Share of reports merged"
              value={`${Math.round(s.dedup_ratio * 100)}%`}
              note="Fewer cases to chase"
            />
          </div>

          <LineChart
            title="Cases per hour"
            xKey="hour"
            rows={s.timeseries}
            series={[
              { key: "reported", label: "Reported", color: SERIES_DARK[0] },
              { key: "assigned", label: "Assigned", color: SERIES_DARK[1] },
              { key: "rescued", label: "Rescued", color: SERIES_DARK[2] },
            ]}
          />

          <div className="grid gap-4 lg:grid-cols-3">
            <BarList
              title="Open cases by urgency"
              items={["critical", "high", "medium", "low"].map((l) => ({
                key: l,
                value: s.by_level[l] ?? 0,
                color: levelColor(l),
                label: (
                  <span className="inline-flex items-center gap-1.5">
                    <span style={{ color: levelColor(l) }}>
                      <LevelGlyph level={l} />
                    </span>
                    {LEVEL_LABEL[l]}
                  </span>
                ),
              }))}
            />
            <BarList
              title="Cases by status"
              items={Object.entries(s.by_status)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => ({
                  key: k,
                  value: v,
                  label: STATUS_LABEL[k] ?? k,
                }))}
            />
            <BarList
              title="Where reports came from"
              items={Object.entries(s.channels)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => ({
                  key: k,
                  value: v,
                  label: CHANNEL_LABEL[k] ?? k,
                }))}
            />
          </div>

          <section className="rounded-xl border border-line bg-panel p-4">
            <h2 className="mb-3 text-[14px] font-semibold">Teams</h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-[13px]">
                <thead className="text-xs text-muted">
                  <tr className="border-b border-line">
                    <th className="py-2 pr-4 font-medium">Team</th>
                    <th className="py-2 pr-4 font-medium">Asset</th>
                    <th className="py-2 pr-4 text-right font-medium">Rescues</th>
                    <th className="py-2 pr-4 text-right font-medium">People</th>
                    <th className="py-2 text-right font-medium">Average travel</th>
                  </tr>
                </thead>
                <tbody className="tnum">
                  {(teams.data ?? []).map((t) => (
                    <tr key={t.call_sign} className="border-b border-line last:border-0">
                      <td className="py-2 pr-4 font-mono">{t.call_sign}</td>
                      <td className="py-2 pr-4 text-muted">{ASSET_LABEL[t.asset_type]}</td>
                      <td className="py-2 pr-4 text-right">{t.completed}</td>
                      <td className="py-2 pr-4 text-right">{t.people_rescued}</td>
                      <td className="py-2 text-right text-muted">
                        {t.avg_travel_min == null ? "None yet" : `${t.avg_travel_min} min`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </FullPage>
  );
}

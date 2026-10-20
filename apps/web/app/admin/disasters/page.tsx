"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Upload } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { type ChangeEvent, useCallback, useState } from "react";
import { AdminTabs } from "@/components/command/admin-tabs";
import { AuditTrail, FloodModel } from "@/components/command/flood-model";
import { FullPage } from "@/components/command/panel";
import { Empty, ErrorNote } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { FormRow, Input, Textarea } from "@/components/ui/field";
import { Dialog } from "@/components/ui/overlay";
import { ApiError, api, type DisasterOut } from "@/lib/api";
import { cn, stamp } from "@/lib/format";
import { keys, useDisasterId, useDisasters, useFloodZones } from "@/lib/queries";
import { useUi } from "@/lib/store";

const DrawMap = dynamic(() => import("@/components/map/draw-map").then((m) => m.DrawMap), { ssr: false });

async function readGeoJson(file: File): Promise<GeoJSON.Geometry[]> {
  const data = JSON.parse(await file.text());
  if (data.type === "FeatureCollection") return data.features.map((f: GeoJSON.Feature) => f.geometry);
  if (data.type === "Feature") return [data.geometry];
  return [data];
}

function CreateDisaster({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const [, setDisaster] = useDisasterId();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [area, setArea] = useState<GeoJSON.Polygon | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onShape = useCallback((p: GeoJSON.Polygon | null) => setArea(p), []);
  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api.post<DisasterOut>("/api/v1/disasters", {
        name,
        description: description || null,
        area,
      });
      await qc.invalidateQueries({ queryKey: keys.disasters });
      setDisaster(d.id);
      toast({
        kind: "success",
        text: `${d.name} is live. Register teams next.`,
      });
      onOpenChange(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the disaster");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title="Start a disaster response"
      description="Public SOS reports and WhatsApp messages go to the newest active disaster whose area contains them."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={create} loading={busy} disabled={name.trim().length < 3}>
            Start response
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <FormRow label="Name" htmlFor="dname">
          <Input
            id="dname"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Chennai floods, November 2026"
          />
        </FormRow>
        <FormRow label="Notes for coordinators" htmlFor="ddesc" hint="Optional">
          <Textarea id="ddesc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </FormRow>
        <div className="space-y-1.5">
          <span className="text-[13px] font-medium">Operational area</span>
          <DrawMap center={[13.0, 80.2]} reference={[]} onShape={onShape} />
        </div>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
      </div>
    </Dialog>
  );
}

function FloodZones({ disaster }: { disaster: DisasterOut }) {
  const zones = useFloodZones(disaster.id);
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const [draw, setDraw] = useState(false);
  const [shape, setShape] = useState<GeoJSON.Polygon | null>(null);
  const [depth, setDepth] = useState("1.0");
  const [name, setName] = useState("");
  const onShape = useCallback((p: GeoJSON.Polygon | null) => setShape(p), []);
  const refresh = () => qc.invalidateQueries({ queryKey: keys.flood(disaster.id) });

  const add = async (geometry: GeoJSON.Geometry, zoneName: string | null, depthM: number | null, source: string) => {
    await api.post(`/api/v1/disasters/${disaster.id}/flood-zones`, {
      geometry,
      name: zoneName,
      depth_estimate_m: depthM,
      source,
    });
  };
  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const geoms = await readGeoJson(file);
      for (const g of geoms) await add(g, file.name.replace(/\.(geo)?json$/i, ""), null, `Uploaded: ${file.name}`);
      toast({
        kind: "success",
        text: `${geoms.length} flood zones added. The plan will avoid them.`,
      });
      refresh();
    } catch (err) {
      toast({
        kind: "error",
        text: err instanceof ApiError ? err.message : "That file is not GeoJSON polygons",
      });
    }
    e.target.value = "";
  };
  return (
    <section className="rounded-xl border border-line bg-panel p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-[15px] font-semibold">Flood zones</h2>
        <span className="text-xs text-muted">Trucks are kept out of deep zones; boats are sent into them.</span>
        <div className="ml-auto flex gap-2">
          <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-line-strong px-3 text-[13px] hover:bg-panel-2">
            <Upload className="size-3.5" /> Upload GeoJSON
            <input type="file" accept=".json,.geojson,application/geo+json" className="hidden" onChange={upload} />
          </label>
          <Button size="sm" variant="subtle" icon={<Plus className="size-3.5" />} onClick={() => setDraw((v) => !v)}>
            Draw a zone
          </Button>
        </div>
      </div>
      {draw ? (
        <div className="mt-4 space-y-3">
          <DrawMap
            center={disaster.center as [number, number] | null}
            reference={(zones.data ?? []).map((z) => z.geometry as unknown as GeoJSON.Geometry)}
            onShape={onShape}
          />
          <div className="flex flex-wrap items-end gap-3">
            <FormRow label="Name" htmlFor="zname">
              <Input
                id="zname"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Mudichur low-lying area"
                className="w-64"
              />
            </FormRow>
            <FormRow label="Depth (m)" htmlFor="zdepth">
              <Input
                id="zdepth"
                type="number"
                min={0}
                max={20}
                step={0.1}
                value={depth}
                onChange={(e) => setDepth(e.target.value)}
                className="w-28"
              />
            </FormRow>
            <Button
              disabled={!shape}
              onClick={async () => {
                if (!shape) return;
                try {
                  await add(shape, name || null, Number(depth), "Drawn by coordinator");
                  toast({ kind: "success", text: "Flood zone added" });
                  setDraw(false);
                  refresh();
                } catch (e) {
                  toast({
                    kind: "error",
                    text: e instanceof ApiError ? e.message : "Could not save the zone",
                  });
                }
              }}
            >
              Save zone
            </Button>
          </div>
        </div>
      ) : null}
      <ul className="mt-4 divide-y divide-line">
        {(zones.data ?? []).map((z) => (
          <li key={z.id} className="flex items-center gap-3 py-2 text-[13px]">
            <span className="size-2.5 rounded-sm bg-water/60" aria-hidden />
            <span className="min-w-0 flex-1 truncate">{z.name ?? "Flood zone"}</span>
            <span className="text-muted tnum">
              {z.depth_estimate_m != null ? `${z.depth_estimate_m} m` : "Depth unknown"}
            </span>
            <span className="hidden max-w-72 truncate text-xs text-faint md:block">{z.source}</span>
            <button
              type="button"
              aria-label={`Delete ${z.name ?? "zone"}`}
              onClick={async () => {
                await api.del(`/api/v1/flood-zones/${z.id}`).catch(() => undefined);
                refresh();
              }}
              className="rounded p-1 text-muted hover:text-critical"
            >
              <Trash2 className="size-3.5" />
            </button>
          </li>
        ))}
        {zones.data?.length === 0 ? (
          <li className="py-3 text-[13px] text-muted">
            No flood zones yet. Without them, depth comes only from what reporters say.
          </li>
        ) : null}
      </ul>
    </section>
  );
}

export default function AdminDisasters() {
  const disasters = useDisasters();
  const [current, setCurrent] = useDisasterId();
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const [create, setCreate] = useState(false);
  const [closing, setClosing] = useState<DisasterOut | null>(null);
  const selected = disasters.data?.find((d) => d.id === current);

  const close = async () => {
    if (!closing) return;
    try {
      await api.patch(`/api/v1/disasters/${closing.id}`, { status: "closed" });
      qc.invalidateQueries({ queryKey: keys.disasters });
      toast({
        kind: "success",
        text: `${closing.name} closed. Personal data is purged in 90 days.`,
      });
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Could not close it",
      });
    }
    setClosing(null);
  };

  return (
    <FullPage
      title="Disasters"
      description="Start a response, draw its area and flood zones, and close it when the water goes down."
      actions={
        <Button icon={<Plus className="size-4" />} onClick={() => setCreate(true)}>
          Start a response
        </Button>
      }
    >
      <AdminTabs />
      <div className="grid gap-5 lg:grid-cols-[22rem_1fr]">
        <section className="rounded-xl border border-line bg-panel">
          {disasters.data?.length === 0 ? <Empty title="No disasters yet" /> : null}
          <ul className="divide-y divide-line">
            {(disasters.data ?? []).map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => setCurrent(d.id)}
                  className={cn("w-full px-4 py-3 text-left", d.id === current ? "bg-panel-2" : "hover:bg-panel-2/60")}
                >
                  <div className="flex items-center gap-2 text-[13px]">
                    <span className="min-w-0 flex-1 truncate font-medium">{d.name}</span>
                    <span
                      className={cn(
                        "text-xs capitalize",
                        d.status === "active" ? "text-go" : d.status === "replay" ? "text-accent-text" : "text-faint",
                      )}
                    >
                      {d.status}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted">
                    Since {stamp(d.started_at)}
                    {d.ended_at ? ` · closed ${stamp(d.ended_at)}` : ""}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </section>
        {selected ? (
          <div className="space-y-5">
            <section className="rounded-xl border border-line bg-panel p-5">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-[17px] font-semibold">{selected.name}</h2>
                <span className="text-xs capitalize text-muted">{selected.status}</span>
                <div className="ml-auto flex gap-2">
                  <Link
                    href="/command"
                    className="inline-flex h-8 items-center rounded-md border border-line-strong px-3 text-[13px] hover:bg-panel-2"
                  >
                    Open the map
                  </Link>
                  {selected.status === "active" ? (
                    <Button size="sm" variant="danger" onClick={() => setClosing(selected)}>
                      Close response
                    </Button>
                  ) : null}
                </div>
              </div>
              {selected.description ? (
                <p className="mt-2 max-w-2xl text-[13px] text-muted">{selected.description}</p>
              ) : null}
            </section>
            <FloodModel disaster={selected} />
            <FloodZones disaster={selected} />
            <AuditTrail disaster={selected} />
          </div>
        ) : null}
      </div>
      <CreateDisaster open={create} onOpenChange={setCreate} />
      <Dialog
        open={!!closing}
        onOpenChange={(v) => !v && setClosing(null)}
        size="sm"
        title={`Close ${closing?.name ?? "this response"}?`}
        description="New SOS reports will no longer reach it. Teams and history stay for the record; phone numbers and medical details are purged after 90 days."
        footer={
          <>
            <Button variant="ghost" onClick={() => setClosing(null)}>
              Keep it open
            </Button>
            <Button variant="danger" onClick={close}>
              Close response
            </Button>
          </>
        }
      />
    </FullPage>
  );
}

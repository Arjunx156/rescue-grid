"use client";

import { FileSpreadsheet, PhoneCall, Upload } from "lucide-react";
import { type DragEvent, type FormEvent, useRef, useState } from "react";
import { useShell } from "@/components/command/context";
import { FullPage } from "@/components/command/panel";
import { ErrorNote } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { FormRow, Input, Textarea } from "@/components/ui/field";
import { ApiError, api, qs } from "@/lib/api";
import { cn } from "@/lib/format";

interface ImportResult {
  rows: number;
  created: number;
  duplicates: number;
  errors: string[];
}

function Importer({ disasterId }: { disasterId: string }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setResult(null);
    setError(null);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    pick(e.dataTransfer.files[0]);
  };
  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.set("disaster_id", disasterId);
    body.set("file", file);
    try {
      setResult(await api.post<ImportResult>("/api/v1/intake/import", body));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="rounded-xl border border-line bg-panel p-5">
      <h2 className="flex items-center gap-2 text-[15px] font-semibold">
        <FileSpreadsheet className="size-4 text-muted" /> Import a volunteer spreadsheet
      </h2>
      <p className="mt-1 text-[13px] text-muted">
        CSV with a message column (text, message or details). Phone, name, address, lat/lng, time and id columns are
        used when present. Re-uploading the same sheet adds nothing twice.
      </p>
      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cn(
          "mt-4 flex w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-10 text-[13px] transition-colors",
          over ? "border-focus bg-accent-soft" : "border-line-strong hover:border-faint",
        )}
      >
        <Upload className="size-5 text-muted" />
        {file ? (
          <span>
            <span className="font-medium text-text">{file.name}</span> · {(file.size / 1024).toFixed(0)} KB
          </span>
        ) : (
          <span className="text-muted">Drop a CSV here, or click to choose one</span>
        )}
      </button>
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(e) => pick(e.target.files?.[0])}
      />
      <div className="mt-4 flex items-center gap-3">
        <Button onClick={upload} disabled={!file} loading={busy}>
          Import messages
        </Button>
        {result ? (
          <output className="block text-[13px] text-muted">
            <span className="text-go tnum">{result.created} new</span> · {result.duplicates} already in · {result.rows}{" "}
            rows read
          </output>
        ) : null}
      </div>
      {error ? (
        <div className="mt-3">
          <ErrorNote>{error}</ErrorNote>
        </div>
      ) : null}
      {result?.errors.length ? (
        <ul className="mt-3 space-y-0.5 text-xs text-medium">
          {result.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function Helpline({ disasterId }: { disasterId: string }) {
  const [text, setText] = useState("");
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ tracking_code: string }>(`/api/v1/intake/manual${qs({ disaster_id: disasterId })}`, {
        text,
        phone: phone || null,
        name: name || null,
      });
      setCode(r.tracking_code);
      setText("");
      setPhone("");
      setName("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not log the call");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="rounded-xl border border-line bg-panel p-5">
      <h2 className="flex items-center gap-2 text-[15px] font-semibold">
        <PhoneCall className="size-4 text-muted" /> Log a helpline call
      </h2>
      <p className="mt-1 text-[13px] text-muted">
        Type what the caller says, in any language. The pipeline reads, locates and scores it like any other report.
      </p>
      <form onSubmit={submit} className="mt-4 space-y-4">
        <FormRow
          label="What is happening, and where"
          htmlFor="msg"
          hint="Headcount, who is vulnerable, water level, landmarks, door number"
        >
          <Textarea
            id="msg"
            required
            minLength={3}
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="4 people incl. elderly mother on oxygen, first floor, near Ganapathy temple, Velachery. Water rising."
          />
        </FormRow>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormRow label="Caller's phone" htmlFor="ph">
            <Input id="ph" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </FormRow>
          <FormRow label="Caller's name" htmlFor="nm">
            <Input id="nm" value={name} onChange={(e) => setName(e.target.value)} />
          </FormRow>
        </div>
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <div className="flex items-center gap-4">
          <Button type="submit" loading={busy}>
            Log the call
          </Button>
          {code ? (
            <output className="block text-[13px] text-muted">
              Read this code to the caller:{" "}
              <span className="font-mono text-[18px] font-semibold tracking-wider text-text">{code}</span>
            </output>
          ) : null}
        </div>
      </form>
    </section>
  );
}

export default function IntakePage() {
  const { disasterId, disaster, canEdit } = useShell();
  return (
    <FullPage
      title="Intake"
      description="WhatsApp messages and the public SOS form arrive on their own. Bring in everything else here."
    >
      {!disasterId || !canEdit ? (
        <p className="text-sm text-muted">Only coordinators can add reports.</p>
      ) : disaster?.status === "closed" ? (
        <p className="text-sm text-muted">This disaster is closed. Choose an active one to add reports.</p>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <Helpline disasterId={disasterId} />
          <Importer disasterId={disasterId} />
        </div>
      )}
    </FullPage>
  );
}

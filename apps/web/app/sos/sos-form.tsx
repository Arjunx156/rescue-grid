"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, LocateFixed, Minus, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { PublicHeader } from "@/components/public-header";
import { ErrorNote } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { FormRow, Input, Textarea } from "@/components/ui/field";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/format";
import type { Key } from "@/lib/i18n";
import { useLang } from "@/lib/use-lang";

const NEEDS: { key: string; label: Key }[] = [
  { key: "rescue", label: "needRescue" },
  { key: "medical", label: "needMedical" },
  { key: "boat", label: "needBoat" },
  { key: "food", label: "needFood" },
  { key: "water", label: "needWater" },
];

type Fix = { lat: number; lng: number; accuracy: number };

export function SosForm() {
  const router = useRouter();
  const [lang, setLang, t] = useLang();
  const [text, setText] = useState("");
  const [people, setPeople] = useState(1);
  const [needs, setNeeds] = useState<string[]>(["rescue"]);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [fix, setFix] = useState<Fix | null>(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const context = useQuery({
    queryKey: ["sos-context"],
    queryFn: () => api.get<{ available: boolean; name: string | null }>("/api/v1/sos/context"),
  });

  const locate = () => {
    if (!("geolocation" in navigator)) {
      setLocError(true);
      return;
    }
    setLocating(true);
    setLocError(false);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setFix({
          lat: p.coords.latitude,
          lng: p.coords.longitude,
          accuracy: p.coords.accuracy,
        });
        setLocating(false);
      },
      () => {
        setLocError(true);
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15_000 },
    );
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ tracking_code: string }>("/api/v1/sos", {
        text,
        people,
        needs,
        phone: phone || null,
        name: name || null,
        lat: fix?.lat ?? null,
        lng: fix?.lng ?? null,
        language: lang,
        website,
      });
      try {
        const mine = JSON.parse(localStorage.getItem("rg:my-requests") ?? "[]") as string[];
        localStorage.setItem("rg:my-requests", JSON.stringify([r.tracking_code, ...mine].slice(0, 10)));
      } catch {
        /* private mode */
      }
      router.push(`/sos/${r.tracking_code}`);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 503
          ? t("noDisaster")
          : err instanceof ApiError && err.status !== 0
            ? err.message
            : t("sendFailed"),
      );
      setBusy(false);
    }
  };

  const unavailable = context.data && !context.data.available;

  return (
    <div className="min-h-dvh bg-bg text-text">
      <PublicHeader lang={lang} onLang={setLang} label={t("language")} />
      <main className="mx-auto w-full max-w-xl px-5 pt-6 pb-16">
        <h1 className="text-[32px] font-semibold leading-tight tracking-tight">{t("sosTitle")}</h1>
        <p className="mt-3 text-[17px] leading-relaxed text-muted">{t("sosIntro")}</p>
        {context.data?.name ? <p className="mt-2 text-[14px] text-muted">{context.data.name}</p> : null}
        {unavailable ? (
          <div className="mt-6">
            <ErrorNote>{t("noDisaster")}</ErrorNote>
          </div>
        ) : null}

        <form onSubmit={submit} className="mt-8 space-y-7">
          <FormRow large label={t("what")} htmlFor="what" hint={t("whatHint")}>
            <Textarea
              id="what"
              required
              minLength={3}
              rows={5}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={t("whatPlaceholder")}
              className="text-[17px]"
            />
          </FormRow>

          <fieldset className="space-y-2">
            <legend className="block text-[15px] font-medium">{t("people")}</legend>
            <div className="flex items-center gap-4">
              <button
                type="button"
                aria-label="One fewer"
                onClick={() => setPeople((n) => Math.max(1, n - 1))}
                className="grid size-12 place-items-center rounded-full border border-line-strong"
              >
                <Minus className="size-5" />
              </button>
              <output className="w-14 text-center text-[32px] font-semibold tnum" aria-live="polite">
                {people}
              </output>
              <button
                type="button"
                aria-label="One more"
                onClick={() => setPeople((n) => Math.min(200, n + 1))}
                className="grid size-12 place-items-center rounded-full border border-line-strong"
              >
                <Plus className="size-5" />
              </button>
            </div>
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-[15px] font-medium">{t("needs")}</legend>
            <div className="flex flex-wrap gap-2 pt-1">
              {NEEDS.map((n) => {
                const on = needs.includes(n.key);
                return (
                  <button
                    key={n.key}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setNeeds((cur) => (on ? cur.filter((x) => x !== n.key) : [...cur, n.key]))}
                    className={cn(
                      "inline-flex h-12 items-center gap-2 rounded-full border px-5 text-[16px] transition-colors",
                      on ? "border-accent bg-accent-soft font-medium text-accent-text" : "border-line-strong",
                    )}
                  >
                    {on ? <Check className="size-4" /> : null}
                    {t(n.label)}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <div className="space-y-2">
            <span className="block text-[15px] font-medium">{t("where")}</span>
            <Button
              type="button"
              variant={fix ? "outline" : "subtle"}
              size="lg"
              className="w-full"
              loading={locating}
              icon={fix ? <Check className="size-5 text-go" /> : <LocateFixed className="size-5" />}
              onClick={locate}
            >
              {locating ? t("locating") : fix ? t("locationAdded") : t("useLocation")}
            </Button>
            <p className={cn("text-[14px]", locError ? "text-high" : "text-muted")}>
              {locError
                ? t("locationDenied")
                : fix
                  ? `${fix.lat.toFixed(5)}, ${fix.lng.toFixed(5)} (±${Math.round(fix.accuracy)} m)`
                  : t("locationHint")}
            </p>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <FormRow large label={t("phone")} htmlFor="phone" hint={t("phoneHint")}>
              <Input
                id="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="h-12 text-[17px]"
              />
            </FormRow>
            <FormRow large label={`${t("name")} (${t("optional")})`} htmlFor="name">
              <Input
                id="name"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-12 text-[17px]"
              />
            </FormRow>
          </div>

          {/* bots fill every field; people never see this one */}
          <div className="absolute -left-[9999px]" aria-hidden>
            <label>
              Website
              <input tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
            </label>
          </div>

          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <Button type="submit" size="xl" variant="primary" loading={busy} disabled={!!unavailable}>
            {busy ? t("sending") : t("send")}
          </Button>
          <p className="text-[14px] text-muted">
            {t("privacy")}{" "}
            <Link href="/privacy" className="text-accent-text underline underline-offset-2">
              {t("privacyMore")}
            </Link>
          </p>
        </form>
      </main>
    </div>
  );
}

"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { Toasts } from "@/components/toasts";
import { ErrorNote, Skeleton } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { FormRow, Input, Select } from "@/components/ui/field";
import { ApiError, api, type UserOut } from "@/lib/api";
import { LANGS, saveLang } from "@/lib/i18n";
import { keys, useMe } from "@/lib/queries";
import { useUi } from "@/lib/store";

export default function SettingsPage() {
  const me = useMe();
  const qc = useQueryClient();
  const router = useRouter();
  const toast = useUi((s) => s.toast);
  const [name, setName] = useState("");
  const [lang, setLang] = useState("en");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notify, setNotify] = useState<NotificationPermission | "unsupported">("default");

  useEffect(() => {
    if (me.data) {
      setName(me.data.name);
      setLang(me.data.preferred_language);
    }
  }, [me.data]);
  useEffect(() => {
    setNotify(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
  }, []);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await api.patch<UserOut>("/api/v1/auth/me", {
        name,
        preferred_language: lang,
      });
      qc.setQueryData(keys.me, u);
      saveLang(lang as never);
      toast({ kind: "success", text: "Saved" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    await api.post("/api/v1/auth/logout").catch(() => undefined);
    qc.clear();
    router.replace("/login");
  };

  const home = me.data?.role === "field_lead" ? "/field" : "/command";
  return (
    <div className="min-h-dvh bg-bg text-text">
      <header className="mx-auto flex max-w-xl items-center gap-3 px-5 pt-6">
        <Link href={home} className="inline-flex items-center gap-1.5 text-[14px] text-muted hover:text-text">
          <ArrowLeft className="size-4" /> Back
        </Link>
        <span className="ml-auto inline-flex items-center gap-2 text-[14px] font-semibold">
          <Logo className="size-4 text-accent" /> Rescue Grid
        </span>
      </header>
      <main className="mx-auto max-w-xl px-5 py-10">
        <h1 className="text-[28px] font-semibold tracking-tight">Settings</h1>
        {me.isLoading ? (
          <Skeleton className="mt-8 h-64 w-full" />
        ) : me.data ? (
          <>
            <p className="mt-2 text-[15px] text-muted">
              {me.data.email ?? me.data.phone} · <span className="capitalize">{me.data.role.replace("_", " ")}</span>
              {me.data.organization ? ` · ${me.data.organization}` : ""}
            </p>
            <form onSubmit={save} className="mt-8 space-y-5">
              <FormRow label="Name" htmlFor="sname">
                <Input id="sname" required value={name} onChange={(e) => setName(e.target.value)} className="h-11" />
              </FormRow>
              <FormRow label="Language for the field app and messages" htmlFor="slang">
                <Select id="slang" value={lang} onChange={(e) => setLang(e.target.value)} className="h-11 font-native">
                  {LANGS.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.name}
                    </option>
                  ))}
                </Select>
              </FormRow>
              {error ? <ErrorNote>{error}</ErrorNote> : null}
              <Button type="submit" loading={busy}>
                Save changes
              </Button>
            </form>
            <section className="mt-12 border-t border-line pt-8">
              <h2 className="text-[17px] font-semibold">Notifications</h2>
              <p className="mt-2 text-[15px] text-muted">
                {notify === "granted"
                  ? "This browser shows alerts for new assignments and critical cases."
                  : notify === "denied"
                    ? "Alerts are blocked for this site. Allow them in the browser's site settings."
                    : notify === "unsupported"
                      ? "This browser cannot show alerts."
                      : "Allow alerts so a new assignment reaches you even when the app is closed."}
              </p>
              {notify === "default" ? (
                <Button
                  className="mt-4"
                  variant="outline"
                  onClick={async () => setNotify(await Notification.requestPermission())}
                >
                  Allow alerts
                </Button>
              ) : null}
            </section>
            <section className="mt-12 border-t border-line pt-8">
              <h2 className="text-[17px] font-semibold">Session</h2>
              <p className="mt-2 text-[15px] text-muted">
                Signing out ends this device's session. An admin can end all of your sessions.
              </p>
              <Button className="mt-4" variant="danger" onClick={signOut}>
                Sign out
              </Button>
            </section>
          </>
        ) : (
          <ErrorNote onRetry={() => me.refetch()}>Could not load your account.</ErrorNote>
        )}
      </main>
      <Toasts />
    </div>
  );
}

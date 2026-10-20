"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Smartphone, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Logo } from "@/components/logo";
import { ErrorNote } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { FormRow, Input } from "@/components/ui/field";
import { ApiError, api, type UserOut } from "@/lib/api";
import { cn } from "@/lib/format";

type Mode = "staff" | "field";

function home(role: string, next: string | null): string {
  if (role === "field_lead") return next?.startsWith("/field") ? next : "/field";
  return next && !next.startsWith("/field") && next.startsWith("/") ? next : "/command";
}

export function LoginForm() {
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [mode, setMode] = useState<Mode>("staff");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState<null | { dev_code: string | null }>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const options = useQuery({
    queryKey: ["auth-options"],
    queryFn: () => api.get<{ demo: boolean; otp_via_whatsapp: boolean }>("/api/v1/auth/options"),
  });

  const run = async (key: string, fn: () => Promise<UserOut>) => {
    setBusy(key);
    setError(null);
    try {
      const user = await fn();
      router.replace(home(user.role, next));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      setBusy(null);
    }
  };

  const signIn = (e: FormEvent) => {
    e.preventDefault();
    run("staff", () => api.post<UserOut>("/api/v1/auth/login", { email, password }));
  };

  const sendCode = async (e: FormEvent) => {
    e.preventDefault();
    setBusy("otp");
    setError(null);
    try {
      const r = await api.post<{ dev_code: string | null }>("/api/v1/auth/otp/request", { phone });
      setCodeSent(r);
      if (r.dev_code) setCode(r.dev_code);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send a code.");
    } finally {
      setBusy(null);
    }
  };

  const verify = (e: FormEvent) => {
    e.preventDefault();
    run("verify", () => api.post<UserOut>("/api/v1/auth/otp/verify", { phone, code }));
  };

  const demo = (role: string) => run(`demo-${role}`, () => api.post<UserOut>("/api/v1/auth/demo", { role }));

  return (
    <main className="grid min-h-dvh bg-bg text-text lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <section className="flex flex-col px-6 py-8 sm:px-12 lg:px-16">
        <Link href="/" className="inline-flex w-fit items-center gap-2 text-[14px] font-semibold">
          <Logo className="size-5 text-signal" />
          Rescue Grid
        </Link>
        <div className="my-auto w-full max-w-sm py-12">
          <h1 className="text-[28px] font-semibold tracking-tight">Sign in</h1>
          <p className="mt-2 text-[15px] text-muted">
            Coordinators use email. Field teams use the phone their coordinator registered.
          </p>

          <div className="mt-8 grid grid-cols-2 gap-1 rounded-lg bg-panel p-1" role="tablist" aria-label="Sign in as">
            {(
              [
                ["staff", "Control room", UserRound],
                ["field", "Field team", Smartphone],
              ] as const
            ).map(([m, label, Icon]) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                onClick={() => {
                  setMode(m);
                  setError(null);
                }}
                className={cn(
                  "flex h-9 items-center justify-center gap-2 rounded-md text-[13px] font-medium transition-colors",
                  mode === m ? "bg-raised text-text shadow-card" : "text-muted hover:text-text",
                )}
              >
                <Icon className="size-4" />
                {label}
              </button>
            ))}
          </div>

          <div className="mt-6 space-y-4">
            {error ? <ErrorNote>{error}</ErrorNote> : null}
            {mode === "staff" ? (
              <form onSubmit={signIn} className="space-y-4">
                <FormRow label="Email" htmlFor="email">
                  <Input
                    id="email"
                    type="email"
                    autoComplete="username"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="h-11"
                  />
                </FormRow>
                <FormRow
                  label="Password"
                  htmlFor="password"
                  hint="Forgot it? Your admin can send you a link to choose a new one."
                >
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="h-11"
                  />
                </FormRow>
                <Button type="submit" size="lg" className="w-full" loading={busy === "staff"}>
                  Sign in
                </Button>
              </form>
            ) : codeSent ? (
              <form onSubmit={verify} className="space-y-4">
                <button
                  type="button"
                  onClick={() => setCodeSent(null)}
                  className="inline-flex items-center gap-1 text-[13px] text-muted hover:text-text"
                >
                  <ArrowLeft className="size-3.5" /> Use a different number
                </button>
                <FormRow
                  label="6-digit code"
                  htmlFor="code"
                  hint={
                    codeSent.dev_code ? "Demo mode: the code is filled in for you." : `Sent on WhatsApp to ${phone}.`
                  }
                >
                  <Input
                    id="code"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="\d{6}"
                    maxLength={6}
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                    className="h-12 text-center font-mono text-xl tracking-[0.5em]"
                  />
                </FormRow>
                <Button type="submit" size="lg" className="w-full" loading={busy === "verify"}>
                  Verify and continue
                </Button>
              </form>
            ) : (
              <form onSubmit={sendCode} className="space-y-4">
                <FormRow label="Team lead's phone" htmlFor="phone" hint="We send a one-time code on WhatsApp.">
                  <Input
                    id="phone"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    placeholder="98400 12345"
                    required
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="h-11"
                  />
                </FormRow>
                <Button type="submit" size="lg" className="w-full" loading={busy === "otp"}>
                  Send code
                </Button>
              </form>
            )}
          </div>

          {options.data?.demo ? (
            <div className="mt-10 border-t border-line pt-6">
              <p className="text-[13px] font-medium">Try the demo</p>
              <p className="mt-1 text-[13px] text-muted">
                Seeded accounts on a live drill. Nothing here reaches real people.
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <Button variant="outline" onClick={() => demo("coordinator")} loading={busy === "demo-coordinator"}>
                  Coordinator
                </Button>
                <Button variant="outline" onClick={() => demo("field_lead")} loading={busy === "demo-field_lead"}>
                  Boat crew
                </Button>
                <Button variant="outline" onClick={() => demo("viewer")} loading={busy === "demo-viewer"}>
                  Viewer
                </Button>
              </div>
            </div>
          ) : null}
        </div>
        <p className="text-xs text-muted">
          Accounts are created by invitation from your disaster management authority.
        </p>
      </section>
      <section aria-hidden className="relative hidden overflow-hidden bg-[#0b0f14] lg:block">
        <LoginArt />
      </section>
    </main>
  );
}

/** A quiet still of the command map: flood corridor, cases, one route. */
function LoginArt() {
  return (
    <svg
      viewBox="0 0 600 800"
      className="absolute inset-0 h-full w-full"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
          <path d="M40 0H0v40" fill="none" stroke="#18202c" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width="600" height="800" fill="url(#grid)" />
      <path
        d="M-20 520C90 470 150 520 240 470s170-150 260-120 120 40 140 20"
        fill="none"
        stroke="#22d3ee"
        strokeOpacity=".18"
        strokeWidth="90"
        strokeLinecap="round"
      />
      <path
        d="M-20 520C90 470 150 520 240 470s170-150 260-120 120 40 140 20"
        fill="none"
        stroke="#22d3ee"
        strokeOpacity=".35"
        strokeWidth="1.5"
      />
      <path d="M130 610 210 520 300 470 390 410" fill="none" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" />
      {[
        [390, 410, "#ef4444", 7],
        [300, 470, "#f97316", 6],
        [455, 360, "#ef4444", 7],
        [220, 430, "#eab308", 5],
        [520, 330, "#f97316", 6],
        [170, 500, "#22c55e", 4.5],
        [340, 520, "#eab308", 5],
        [260, 560, "#22c55e", 4.5],
      ].map(([x, y, c, r]) => (
        <g key={`${x}-${y}`}>
          {c === "#ef4444" ? (
            <circle cx={x} cy={y} r={Number(r) + 10} fill="none" stroke={String(c)} strokeOpacity=".35" />
          ) : null}
          <circle cx={x} cy={y} r={r} fill={String(c)} />
        </g>
      ))}
      <path d="m130 598 8 18-8-4-8 4Z" fill="#3b82f6" transform="rotate(40 130 610)" />
    </svg>
  );
}

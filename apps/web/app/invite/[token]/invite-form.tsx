"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Logo } from "@/components/logo";
import { ErrorNote, Skeleton } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { FormRow, Input } from "@/components/ui/field";
import { ApiError, api } from "@/lib/api";

interface InviteInfo {
  email: string;
  name: string;
  role: string;
  organization: string | null;
  reset: boolean;
}

export function InviteForm() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const info = useQuery({
    queryKey: ["invite", token],
    queryFn: () => api.get<InviteInfo>(`/api/v1/auth/invite/${encodeURIComponent(token)}`),
    retry: false,
  });
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mismatch = confirm.length > 0 && confirm !== password;

  const accept = async (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirm) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/v1/auth/invite/accept", { token, password });
      router.replace("/command");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your password");
      setBusy(false);
    }
  };

  return (
    <main className="min-h-dvh bg-bg px-6 py-10 text-text">
      <Link href="/" className="inline-flex items-center gap-2 text-[15px] font-semibold">
        <Logo className="size-5 text-accent" /> Rescue Grid
      </Link>
      <div className="mx-auto mt-16 max-w-sm">
        {info.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : info.error ? (
          <>
            <h1 className="text-[26px] font-semibold tracking-tight">This link cannot be used</h1>
            <p className="mt-3 text-[15px] text-muted">
              It has expired or was already used. Ask your admin for a new one.
            </p>
            <Link href="/login" className="mt-6 inline-block text-[15px] font-medium text-accent-text">
              Go to sign in
            </Link>
          </>
        ) : info.data ? (
          <>
            <h1 className="text-[26px] font-semibold tracking-tight">
              {info.data.reset ? "Choose a new password" : `Welcome, ${info.data.name}`}
            </h1>
            <p className="mt-3 text-[15px] text-muted">
              {info.data.reset
                ? `For ${info.data.email}. Saving it signs this account out everywhere else.`
                : `You are joining ${info.data.organization ?? "Rescue Grid"} as a ${info.data.role}. Choose a password for ${info.data.email}.`}
            </p>
            <form onSubmit={accept} className="mt-8 space-y-4">
              <FormRow
                label={info.data.reset ? "New password" : "Password"}
                htmlFor="pw"
                hint="At least 10 characters. A short sentence works well."
              >
                <Input
                  id="pw"
                  type="password"
                  autoComplete="new-password"
                  minLength={10}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-11"
                />
              </FormRow>
              <FormRow label="Type it again" htmlFor="pw2" error={mismatch ? "The two passwords are different" : null}>
                <Input
                  id="pw2"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  aria-invalid={mismatch || undefined}
                  className="h-11"
                />
              </FormRow>
              {error ? <ErrorNote>{error}</ErrorNote> : null}
              <Button
                type="submit"
                size="lg"
                className="w-full"
                loading={busy}
                disabled={mismatch || password.length < 10}
              >
                {info.data.reset ? "Save and sign in" : "Create my account"}
              </Button>
            </form>
          </>
        ) : null}
      </div>
    </main>
  );
}

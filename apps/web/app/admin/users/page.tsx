"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, UserPlus } from "lucide-react";
import { type FormEvent, useState } from "react";
import { AdminTabs } from "@/components/command/admin-tabs";
import { FullPage } from "@/components/command/panel";
import { ErrorNote, Skeleton } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { FormRow, Input, Select } from "@/components/ui/field";
import { Dialog } from "@/components/ui/overlay";
import { ApiError, api, type UserOut } from "@/lib/api";
import { stamp } from "@/lib/format";
import { useMe } from "@/lib/queries";
import { useUi } from "@/lib/store";

interface Invite {
  id: string;
  email: string;
  name: string;
  role: string;
  expires_at: string;
  accepted_at: string | null;
  link?: string | null;
}

const ROLE_LABEL: Record<string, string> = {
  admin: "Admin",
  coordinator: "Coordinator",
  viewer: "Viewer",
  field_lead: "Field lead",
};

/** A link shown once: the server keeps only its hash, so this is the admin's one chance to copy it. */
function OneTimeLink({ link, note, onDone }: { link: string; note: string; onDone: () => void }) {
  const toast = useUi((s) => s.toast);
  return (
    <div className="space-y-3">
      <p className="text-[13px] text-muted">{note}</p>
      <div className="flex items-center gap-2 rounded-md border border-line bg-bg px-3 py-2">
        <code className="min-w-0 flex-1 truncate text-xs">{link}</code>
        <button
          type="button"
          aria-label="Copy link"
          onClick={() => {
            navigator.clipboard?.writeText(link);
            toast({ kind: "info", text: "Link copied" });
          }}
          className="text-muted hover:text-text"
        >
          <Copy className="size-4" />
        </button>
      </div>
      <div className="flex justify-end">
        <Button onClick={onDone}>Done</Button>
      </div>
    </div>
  );
}

function InviteDialog({
  open,
  onOpenChange,
  onDone,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onDone: () => void;
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("coordinator");
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<Invite>("/api/v1/admin/invites", {
        email,
        name,
        role,
      });
      setLink(r.link ?? null);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the invite");
    } finally {
      setBusy(false);
    }
  };
  const close = (v: boolean) => {
    onOpenChange(v);
    if (!v) {
      setLink(null);
      setEmail("");
      setName("");
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={close}
      title="Invite a staff member"
      description="Field leads are added from the Teams page with their phone number."
    >
      {link ? (
        <OneTimeLink
          link={link}
          note={`Send this link to ${name}. It works once, for 7 days, and is not shown again.`}
          onDone={() => close(false)}
        />
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <FormRow label="Name" htmlFor="iname">
            <Input id="iname" required value={name} onChange={(e) => setName(e.target.value)} />
          </FormRow>
          <FormRow label="Work email" htmlFor="iemail">
            <Input id="iemail" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </FormRow>
          <FormRow
            label="Role"
            htmlFor="irole"
            hint="Viewers see the map and analytics, never phone numbers or medical details."
          >
            <Select id="irole" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="coordinator">Coordinator</option>
              <option value="viewer">Viewer</option>
              <option value="admin">Admin</option>
            </Select>
          </FormRow>
          {error ? <ErrorNote>{error}</ErrorNote> : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => close(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={busy}>
              Create invite link
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

export default function AdminUsers() {
  const me = useMe();
  const qc = useQueryClient();
  const toast = useUi((s) => s.toast);
  const [open, setOpen] = useState(false);
  const [reset, setReset] = useState<{ name: string; link: string } | null>(null);
  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => api.get<UserOut[]>("/api/v1/admin/users"),
  });
  const invites = useQuery({
    queryKey: ["admin-invites"],
    queryFn: () => api.get<Invite[]>("/api/v1/admin/invites"),
  });
  const patch = async (u: UserOut, body: Record<string, unknown>, text: string) => {
    try {
      await api.patch(`/api/v1/admin/users/${u.id}`, body);
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      toast({ kind: "success", text });
    } catch (e) {
      toast({
        kind: "error",
        text: e instanceof ApiError ? e.message : "Could not update",
      });
    }
  };
  const resetLink = async (u: UserOut) => {
    try {
      const r = await api.post<Invite>(`/api/v1/admin/users/${u.id}/reset-link`);
      if (r.link) setReset({ name: u.name, link: r.link });
    } catch (e) {
      toast({ kind: "error", text: e instanceof ApiError ? e.message : "Could not create a reset link" });
    }
  };
  const pendingInvites = (invites.data ?? []).filter((i) => !i.accepted_at);
  return (
    <FullPage
      title="People"
      description="Who can sign in, and what they can see. Accounts are by invitation only."
      actions={
        <Button icon={<UserPlus className="size-4" />} onClick={() => setOpen(true)}>
          Invite
        </Button>
      }
    >
      <AdminTabs />
      {users.error ? <ErrorNote onRetry={() => users.refetch()}>Could not load people.</ErrorNote> : null}
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[820px] text-left text-[13px]">
          <thead className="bg-panel text-xs text-muted">
            <tr className="border-b border-line">
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Sign-in</th>
              <th className="px-4 py-2 font-medium">Organisation</th>
              <th className="px-4 py-2 font-medium">Role</th>
              <th className="px-4 py-2 font-medium">Last seen</th>
              <th className="px-4 py-2 font-medium">Access</th>
            </tr>
          </thead>
          <tbody>
            {users.isLoading ? (
              <tr>
                <td colSpan={6} className="p-4">
                  <Skeleton className="h-24 w-full" />
                </td>
              </tr>
            ) : (
              (users.data ?? []).map((u) => (
                <tr key={u.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-2.5 font-medium">{u.name}</td>
                  <td className="px-4 font-mono text-xs text-muted">{u.email ?? u.phone}</td>
                  <td className="px-4 text-muted">{u.organization ?? ""}</td>
                  <td className="px-4">
                    {u.role === "field_lead" || u.id === me.data?.id ? (
                      ROLE_LABEL[u.role]
                    ) : (
                      <Select
                        value={u.role}
                        onChange={(e) =>
                          patch(u, { role: e.target.value }, `${u.name} is now ${ROLE_LABEL[e.target.value]}`)
                        }
                        className="h-8 w-36"
                        aria-label={`Role for ${u.name}`}
                      >
                        <option value="coordinator">Coordinator</option>
                        <option value="viewer">Viewer</option>
                        <option value="admin">Admin</option>
                      </Select>
                    )}
                  </td>
                  <td className="px-4 text-muted tnum">{u.last_login_at ? stamp(u.last_login_at) : "Never"}</td>
                  <td className="px-4">
                    {u.id === me.data?.id ? (
                      <span className="text-muted">You</span>
                    ) : (
                      <div className="flex items-center gap-2">
                        <Button
                          size="xs"
                          variant={u.is_active ? "ghost" : "subtle"}
                          onClick={() =>
                            patch(
                              u,
                              { is_active: !u.is_active },
                              u.is_active ? `${u.name} can no longer sign in` : `${u.name} can sign in again`,
                            )
                          }
                        >
                          {u.is_active ? "Disable" : "Enable"}
                        </Button>
                        <Button
                          size="xs"
                          variant="ghost"
                          onClick={async () => {
                            await api.del(`/api/v1/admin/users/${u.id}/sessions`).catch(() => undefined);
                            toast({
                              kind: "info",
                              text: `Signed ${u.name} out everywhere`,
                            });
                          }}
                        >
                          Sign out everywhere
                        </Button>
                        {u.email && u.is_active ? (
                          <Button size="xs" variant="ghost" onClick={() => resetLink(u)}>
                            Reset password
                          </Button>
                        ) : null}
                      </div>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {pendingInvites.length ? (
        <section className="mt-6">
          <h2 className="mb-2 text-[14px] font-semibold">Pending invites</h2>
          <ul className="divide-y divide-line rounded-xl border border-line">
            {pendingInvites.map((i) => (
              <li key={i.id} className="flex items-center gap-3 px-4 py-2.5 text-[13px]">
                <span className="font-medium">{i.name}</span>
                <span className="font-mono text-xs text-muted">{i.email}</span>
                <span className="text-muted">{ROLE_LABEL[i.role]}</span>
                <span className="ml-auto text-xs text-faint">Expires {stamp(i.expires_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <Dialog
        open={reset != null}
        onOpenChange={(v) => !v && setReset(null)}
        title={`Reset ${reset?.name ?? ""}'s password`}
      >
        {reset ? (
          <OneTimeLink
            link={reset.link}
            note={`Send this link to ${reset.name}. It works once, for 24 hours. Choosing a new password signs them out everywhere.`}
            onDone={() => setReset(null)}
          />
        ) : null}
      </Dialog>
      <InviteDialog
        open={open}
        onOpenChange={setOpen}
        onDone={() => qc.invalidateQueries({ queryKey: ["admin-invites"] })}
      />
    </FullPage>
  );
}

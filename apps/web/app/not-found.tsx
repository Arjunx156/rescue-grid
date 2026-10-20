import Link from "next/link";
import { Logo } from "@/components/logo";

export default function NotFound() {
  return (
    <main className="grid min-h-dvh place-items-center bg-bg px-6 text-text">
      <div className="max-w-md text-center">
        <Logo className="mx-auto size-8 text-accent" />
        <h1 className="mt-6 text-[28px] font-semibold tracking-tight">This page does not exist</h1>
        <p className="mt-3 text-[16px] text-muted">
          The link may be mistyped, or the case it pointed to was merged into another.
        </p>
        <div className="mt-8 flex justify-center gap-3 text-[15px] font-medium">
          <Link href="/sos" className="rounded-md bg-accent px-4 py-2.5 text-white">
            Report an emergency
          </Link>
          <Link href="/" className="rounded-md border border-line-strong px-4 py-2.5">
            Go home
          </Link>
        </div>
      </div>
    </main>
  );
}

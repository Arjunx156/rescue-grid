"use client";

import { useEffect } from "react";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <main className="grid min-h-dvh place-items-center bg-bg px-6 text-text">
      <div className="max-w-md text-center">
        <h1 className="text-[26px] font-semibold tracking-tight">Something went wrong on this screen</h1>
        <p className="mt-3 text-[16px] text-muted">
          Your data is safe on the server. Try again; if it keeps happening, reload the page.
          {error.digest ? (
            <span className="mt-2 block font-mono text-xs text-faint">Reference {error.digest}</span>
          ) : null}
        </p>
        <button
          type="button"
          onClick={reset}
          className="mt-8 rounded-md bg-accent px-4 py-2.5 text-[15px] font-medium text-white"
        >
          Try again
        </button>
      </div>
    </main>
  );
}

"use client";

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          display: "grid",
          placeItems: "center",
          minHeight: "100vh",
          margin: 0,
        }}
      >
        <div style={{ textAlign: "center", maxWidth: 420, padding: 24 }}>
          <h1 style={{ fontSize: 24 }}>Rescue Grid could not load</h1>
          <p style={{ color: "#4b5563" }}>If you need help now, call 112.</p>
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: 16,
              padding: "10px 16px",
              background: "#2563eb",
              color: "#fff",
              border: 0,
              borderRadius: 6,
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}

import type { NextConfig } from "next";

const API = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const origin = (url: string | undefined) => {
  try {
    return url ? new URL(url).origin : "";
  } catch {
    return "";
  }
};

// map styles, tiles, glyphs and sprites all come from the style's host
const maps = [
  "https://tiles.openfreemap.org",
  origin(process.env.NEXT_PUBLIC_MAP_STYLE_DARK),
  origin(process.env.NEXT_PUBLIC_MAP_STYLE_LIGHT),
];
const live = origin(process.env.NEXT_PUBLIC_WS_URL);
const sources = (...list: string[]) => [...new Set(list.filter(Boolean))].join(" ");

const csp = [
  "default-src 'self'",
  // Next streams hydration data in inline scripts; nonces would make every page dynamic
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  `img-src ${sources("'self'", "data:", "blob:", ...maps)}`,
  "font-src 'self'",
  `connect-src ${sources("'self'", ...maps, live)}`,
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  // dev needs eval for fast refresh, so the policy applies to production builds
  ...(process.env.NODE_ENV === "production" ? [{ key: "Content-Security-Policy", value: csp }] : []),
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(self)",
  },
];

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  reactCompiler: true,
  output: "standalone",
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // one origin for the browser: cookies, CSRF and CORS stay simple
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API}/api/:path*` },
      { source: "/health", destination: `${API}/health` },
    ];
  },
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      {
        source: "/sw.js",
        headers: [{ key: "Cache-Control", value: "no-cache" }],
      },
    ];
  },
};

export default nextConfig;

import type { Metadata, Viewport } from "next";
import {
  Inter,
  JetBrains_Mono,
  Noto_Sans_Devanagari,
  Noto_Sans_Malayalam,
  Noto_Sans_Tamil,
  Noto_Sans_Telugu,
} from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});
// only tracking codes and call signs use it; not worth a preload on every page
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
  preload: false,
});
// regional scripts load only when a page actually renders their characters
const tamil = Noto_Sans_Tamil({
  subsets: ["tamil"],
  variable: "--font-ta",
  display: "swap",
  preload: false,
});
const deva = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  variable: "--font-hi",
  display: "swap",
  preload: false,
});
const mal = Noto_Sans_Malayalam({
  subsets: ["malayalam"],
  variable: "--font-ml",
  display: "swap",
  preload: false,
});
const tel = Noto_Sans_Telugu({
  subsets: ["telugu"],
  variable: "--font-te",
  display: "swap",
  preload: false,
});

const SITE = process.env.PUBLIC_BASE_URL ?? "http://localhost:3100";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: "Rescue Grid", template: "%s · Rescue Grid" },
  description:
    "Rescue Grid turns thousands of chaotic flood SOS messages into a live, prioritised rescue plan: located, de-duplicated, scored and dispatched.",
  applicationName: "Rescue Grid",
  authors: [{ name: "Arjun Krishnan", url: "https://github.com/Arjunx156" }],
  creator: "Arjun Krishnan",
  keywords: ["flood rescue", "disaster response", "SOS triage", "Chennai floods", "dispatch optimisation"],
  openGraph: {
    type: "website",
    siteName: "Rescue Grid",
    title: "Rescue Grid",
    description: "From thousands of flood SOS messages to a live, prioritised rescue plan.",
  },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0f14" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${mono.variable} ${tamil.variable} ${deva.variable} ${mal.variable} ${tel.variable}`}
    >
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

import type { MetadataRoute } from "next";

const SITE = process.env.PUBLIC_BASE_URL ?? "http://localhost:3100";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE}/`, changeFrequency: "monthly", priority: 1 },
    { url: `${SITE}/sos`, changeFrequency: "monthly", priority: 0.9 },
    { url: `${SITE}/privacy`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE}/terms`, changeFrequency: "yearly", priority: 0.3 },
  ];
}

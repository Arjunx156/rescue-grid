import type { MetadataRoute } from "next";

const SITE = process.env.PUBLIC_BASE_URL ?? "http://localhost:3100";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/sos"],
        disallow: ["/command", "/field", "/admin", "/settings", "/invite", "/sos/", "/api"],
      },
    ],
    sitemap: `${SITE}/sitemap.xml`,
  };
}

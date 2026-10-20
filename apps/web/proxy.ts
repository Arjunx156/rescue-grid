import { type NextRequest, NextResponse } from "next/server";

/**
 * Optimistic routing only: the role cookie decides where a signed-in person lands.
 * The API checks every request itself; nothing here grants access.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const role = request.cookies.get("rg_role")?.value;
  if (!role) {
    const url = new URL("/login", request.url);
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  if (role === "field_lead" && !pathname.startsWith("/field") && !pathname.startsWith("/settings")) {
    return NextResponse.redirect(new URL("/field", request.url));
  }
  if (role !== "field_lead" && pathname.startsWith("/field")) {
    return NextResponse.redirect(new URL("/command", request.url));
  }
  if (role !== "admin" && pathname.startsWith("/admin")) {
    return NextResponse.redirect(new URL("/command", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/command/:path*", "/field/:path*", "/admin/:path*", "/settings"],
};

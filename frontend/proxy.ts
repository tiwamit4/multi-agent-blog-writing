/** Forward browser API requests to the existing Python backend. */
export function createApiProxy(apiBaseUrl: string) {
  const backend = new URL(apiBaseUrl);
  if (!["http:", "https:"].includes(backend.protocol)) {
    throw new Error("API_BASE_URL must use HTTP or HTTPS.");
  }

  return async (request: Request): Promise<Response> => {
    const incoming = new URL(request.url);
    const target = new URL(backend);
    target.pathname = backend.pathname.replace(/\/$/, "") + incoming.pathname.slice(4);
    target.search = incoming.search;

    try {
      const upstream = new Request(target, request);
      upstream.headers.delete("host");
      return await fetch(upstream, {
        redirect: "manual",
        signal: AbortSignal.timeout(15_000),
      });
    } catch {
      return Response.json(
        { detail: "The blog API is unavailable. Please try again." },
        { status: 502 },
      );
    }
  };
}

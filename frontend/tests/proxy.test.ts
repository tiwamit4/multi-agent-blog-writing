import { describe, expect, test } from "bun:test";
import { createApiProxy } from "../proxy";

describe("Python API proxy", () => {
  test("preserves GET paths, query parameters, and backend responses", async () => {
    const backend = Bun.serve({
      hostname: "127.0.0.1", port: 0,
      fetch(request) {
        const url = new URL(request.url);
        return Response.json({ path: url.pathname, limit: url.searchParams.get("limit") });
      },
    });
    try {
      const response = await createApiProxy(backend.url.href)(
        new Request("http://frontend/api/runs?limit=5"),
      );
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({ path: "/runs", limit: "5" });
    } finally { backend.stop(true); }
  });

  test("forwards POST JSON and preserves validation errors", async () => {
    const backend = Bun.serve({
      hostname: "127.0.0.1", port: 0,
      async fetch(request) {
        expect(request.method).toBe("POST");
        expect(request.headers.get("content-type")).toBe("application/json");
        expect(request.headers.get("host")).toBe(backend.url.host);
        expect(await request.json()).toEqual({ topic: "AI agents" });
        return Response.json({ detail: "Invalid outline" }, { status: 422 });
      },
    });
    try {
      const response = await createApiProxy(backend.url.href)(new Request(
        "http://frontend/api/runs/evidence", {
          method: "POST", headers: { "Content-Type": "application/json", Host: "frontend" },
          body: JSON.stringify({ topic: "AI agents" }),
        },
      ));
      expect(response.status).toBe(422);
      expect(await response.json()).toEqual({ detail: "Invalid outline" });
    } finally { backend.stop(true); }
  });

  test("keeps double-slash paths on the configured backend", async () => {
    const backend = Bun.serve({
      hostname: "127.0.0.1", port: 0,
      fetch(request) {
        const url = new URL(request.url);
        return Response.json({ host: url.host, path: url.pathname });
      },
    });
    try {
      const response = await createApiProxy(backend.url.href)(
        new Request("http://frontend/api//example.invalid/runs"),
      );
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({
        host: backend.url.host, path: "/example.invalid/runs",
      });
    } finally { backend.stop(true); }
  });

  test("returns a useful error when the backend is unavailable", async () => {
    const backend = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response() });
    const url = backend.url.href;
    backend.stop(true);
    const response = await createApiProxy(url)(new Request("http://frontend/api/runs"));
    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ detail: "The blog API is unavailable. Please try again." });
  });
});

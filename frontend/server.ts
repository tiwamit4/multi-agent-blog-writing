import homepage from "./index.html";
import { createApiProxy } from "./proxy";

// Production HTML manifests resolve assets beside the bundled server file.
if (process.env.NODE_ENV === "production") {
  process.chdir(import.meta.dir);
}

const server = Bun.serve({
  hostname: process.env.HOST ?? "127.0.0.1",
  port: Number(process.env.PORT ?? 5173),
  development: process.env.NODE_ENV === "production"
    ? false
    : { hmr: true, console: true },
  routes: {
    "/api/*": createApiProxy(process.env.API_BASE_URL ?? "http://127.0.0.1:8000"),
    "/*": homepage,
  },
});

console.log(`Blog Writer frontend: ${server.url}`);

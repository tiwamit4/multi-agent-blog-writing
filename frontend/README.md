# Bun frontend

This React/TypeScript frontend uses Bun's native HTTP server, HTML bundler,
and hot reloading. The Python backend runs separately.

## Source code

- `server.ts`: Bun server, frontend bundling, and API routing.
- `proxy.ts`: forwards `/api/*` requests to the Python API.
- `index.html`: HTML entry point imported by Bun.
- `src/main.tsx`: mounts React.
- `src/App.tsx`: blog workflow UI.
- `src/api.ts`: browser requests to `/api`.

## Development

Install Bun 1.4.3+ and open a new terminal. From this directory:

```powershell
bun install --frozen-lockfile
bun run dev
```

Open http://localhost:5173. Start the API from the project root in a separate terminal:

```powershell
python -m uvicorn api.main:app --reload
```

To change the frontend port or backend URL, copy `.env.example` to `.env` in this
directory and edit `PORT` or `API_BASE_URL`. Backend credentials stay in the
project root's `.env` file.

## Validation and production

```powershell
bun test
bun run build
bun run start
```

The production server loads its bundled frontend from `dist/server.js` and
serves it on the same configurable port. Keep the Python API running separately.

# Bun frontend

This React/TypeScript frontend uses Bun's native HTTP server, HTML bundler,
and hot reloading. It offers both Blog Writer and Topic Discovery workspaces.
Topic Discovery ranks sourced ideas and can send a selected topic to Blog Writer.
The Python backend runs separately.

## Source code

- `server.ts`: Bun server, frontend bundling, and API routing.
- `proxy.ts`: forwards `/api/*` requests to the Python API.
- `index.html`: HTML entry point imported by Bun.
- `src/main.tsx`: mounts React.
- `src/App.tsx`: workspace switcher and blog workflow UI.
- `src/DiscoveryWorkspace.tsx`: topic scouting, ranked ideas, and blog handoff.
- `src/api.ts`: browser requests to `/api`.

## Development

Install Bun 1.4.3+ and open a new terminal. From this directory:

```powershell
bun install --frozen-lockfile
bun run dev
```

Open http://localhost:5173. Start the API from the project root in a separate terminal:

```powershell
cd ..\backend
python -m uvicorn api.main:app --reload
```

To change the frontend port or backend URL, create `frontend/.env` with the
settings you need. For local development, the defaults are:

```dotenv
HOST=127.0.0.1
PORT=5173
API_BASE_URL=http://127.0.0.1:8000
```

Backend credentials stay in `backend/.env`.

## Validation and production

```powershell
bun test
bun run build
bun run start
```

The production server loads its bundled frontend from `dist/server.js` and
serves it on the same configurable port. Keep the Python API running separately.

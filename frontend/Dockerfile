# syntax=docker/dockerfile:1

FROM oven/bun:1.4.3 AS build

WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .
RUN bun run build

FROM oven/bun:1.4.3-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=5173

COPY --from=build --chown=bun:bun /app/dist ./dist

USER bun
EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD bun -e "const response = await fetch('http://127.0.0.1:5173/'); if (!response.ok) process.exit(1)"

CMD ["bun", "./dist/server.js"]

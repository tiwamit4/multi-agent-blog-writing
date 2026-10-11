FROM oven/bun:1.4.3 AS build

WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .
RUN bun run build

FROM oven/bun:1.4.3 AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=5173

COPY --from=build --chown=bun:bun /app/dist ./dist

USER bun
EXPOSE 5173

CMD ["bun", "./dist/server.js"]

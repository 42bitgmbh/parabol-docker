# This file is materialized by prepare-source.py; placeholders fail closed.
FROM node:24.19.0-trixie-slim@sha256:ab3eebe934147fee049b5eb83c570f68c849a13c930bdfa482de99fcdfa3b3de AS build
ARG BUILD_HEAP_MB=3072
ENV CI=true HUSKY=0 PARABOL_SOURCE_SHA=@@SOURCE_COMMIT@@
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git python3 build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN corepack enable && corepack prepare pnpm@12.5.1 --activate \
    && mkdir -p /home/node/parabol && chown node:node /home/node/parabol
WORKDIR /home/node/parabol
COPY --chown=node:node . .
USER node
RUN git config --global url."https://github.com/enahum/redux-offline.git".insteadOf "git@github.com:enahum/redux-offline.git" \
    && pnpm install --frozen-lockfile --prod=false --child-concurrency=1 \
    && node --experimental-strip-types --test docker/selfhost/resolve-public-path.test.mjs \
    && cp docker/images/parabol-ubi/environments/pipeline .env \
    && NODE_OPTIONS="--max-old-space-size=${BUILD_HEAP_MB}" node docker/selfhost/build.cjs \
    && test -s dist/web.js && test -s dist/preDeploy.js && test -d build

FROM node:24.19.0-trixie-slim@sha256:ab3eebe934147fee049b5eb83c570f68c849a13c930bdfa482de99fcdfa3b3de AS runtime
ARG BUILD_REVISION
ENV HOME=/home/node USER=node FONTCONFIG_PATH=/etc/fonts PORT=3000 NODE_ENV=production
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /home/node/parabol/self-hosted \
    && chown node:node /home/node/parabol/self-hosted
WORKDIR /home/node/parabol
COPY --from=build --chown=node:node /home/node/parabol/dist ./dist
COPY --from=build --chown=node:node /home/node/parabol/build ./build
COPY --chown=node:node .env.example pnpm-lock.yaml ./
COPY --chown=node:node static/fonts /usr/share/fonts
COPY --chown=node:node docker/images/parabol-ubi/tools/ip-to-server_id /home/node/tools/ip-to-server_id
COPY --chmod=755 docker/selfhost/entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENV DD_GIT_REPOSITORY_URL=https://github.com/ParabolInc/parabol \
    DD_GIT_COMMIT_SHA=@@SOURCE_COMMIT@@ PARABOL_SOURCE_SHA=@@SOURCE_COMMIT@@ PARABOL_SOURCE_VERSION=@@SOURCE_TAG@@
LABEL org.opencontainers.image.title="parabol" \
      org.opencontainers.image.source="https://github.com/ParabolInc/parabol" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.version="@@SOURCE_TAG@@" \
      org.parabol.source.revision="@@SOURCE_COMMIT@@" \
      org.parabol.source.version="@@SOURCE_TAG@@"
USER node
EXPOSE 3000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["node", "./dist/web.js"]

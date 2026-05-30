# Build stage
FROM node:18-alpine AS builder

RUN apk add --no-cache python3 make g++ libc6-compat

WORKDIR /app

ARG SKIP_QUALITY_CHECKS=false

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTANT: Every NEXT_PUBLIC_* variable used in the Next.js app MUST be
# declared below as an ARG + ENV pair. Docker silently ignores --build-arg
# values for undeclared ARGs — the build succeeds, but Next.js sees `undefined`
# at build time and the feature is wrong-but-running (not a build error).
#
# When adding a new NEXT_PUBLIC_ variable:
#   1. Add it to this Dockerfile (ARG line + ENV line below)
#   2. Add it to the FIREBASE_ENV secret format (see docs/ops/secrets.md)
#   3. Add it to cloudbuild.yaml's --build-arg list in get-firebase-config.sh
# ─────────────────────────────────────────────────────────────────────────────
# Firebase config (injected from Secret Manager via get-firebase-config.sh)
ARG NEXT_PUBLIC_FIREBASE_API_KEY
ARG NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ARG NEXT_PUBLIC_FIREBASE_PROJECT_ID
ARG NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET
ARG NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID
ARG NEXT_PUBLIC_FIREBASE_APP_ID
ARG NEXT_PUBLIC_ADMIN_EMAIL
ARG NEXT_PUBLIC_BACKEND_URL
ARG NEXT_PUBLIC_MCP_SANDBOX_URL
# Auth + branding (fork-configurable; see docs/ops/secrets.md)
ARG NEXT_PUBLIC_AUTH_MODE
ARG NEXT_PUBLIC_APP_SLUG
ARG NEXT_PUBLIC_CITATION_SCHEME
ARG MAILGUN_WEBHOOK_SECRET

ENV NEXT_PUBLIC_FIREBASE_API_KEY=$NEXT_PUBLIC_FIREBASE_API_KEY
ENV NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=$NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
ENV NEXT_PUBLIC_FIREBASE_PROJECT_ID=$NEXT_PUBLIC_FIREBASE_PROJECT_ID
ENV NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=$NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET
ENV NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=$NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID
ENV NEXT_PUBLIC_FIREBASE_APP_ID=$NEXT_PUBLIC_FIREBASE_APP_ID
ENV NEXT_PUBLIC_ADMIN_EMAIL=$NEXT_PUBLIC_ADMIN_EMAIL
ENV NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL
ENV NEXT_PUBLIC_MCP_SANDBOX_URL=$NEXT_PUBLIC_MCP_SANDBOX_URL
ENV NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE
ENV NEXT_PUBLIC_APP_SLUG=$NEXT_PUBLIC_APP_SLUG
ENV NEXT_PUBLIC_CITATION_SCHEME=$NEXT_PUBLIC_CITATION_SCHEME
ENV MAILGUN_WEBHOOK_SECRET=$MAILGUN_WEBHOOK_SECRET

COPY package*.json ./
RUN npm cache clean --force && npm ci --no-audit --no-fund

COPY . .

# Quality checks (lint + typecheck + tests)
RUN if [ "$SKIP_QUALITY_CHECKS" != "true" ]; then \
      echo "Running quality checks..." && \
      npm run lint && \
      npx tsc --noEmit && \
      echo "Quality checks passed!"; \
    else \
      echo "Skipping quality checks"; \
    fi

# Build
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Production stage
FROM node:18-alpine

WORKDIR /app

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_OPTIONS="--dns-result-order=ipv4first"
ENV PORT=8080

EXPOSE 8080

CMD ["node", "server.js"]

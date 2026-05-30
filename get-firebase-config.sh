#!/bin/bash

# Fetch Firebase config from Secret Manager and generate Docker build args.
# Used by Cloud Build to inject NEXT_PUBLIC_ env vars into the frontend build.

gcloud secrets versions access latest --secret=FIREBASE_ENV --project $_PROJECT_ID > .env.local

# Parse env file and create build args for Docker
DOCKER_ARGS=$(grep -E "^(NEXT_PUBLIC_|MAILGUN_WEBHOOK_SECRET)" .env.local | sed 's/^/--build-arg /' | tr '\n' ' ')
DOCKER_ARGS="$DOCKER_ARGS --build-arg SKIP_QUALITY_CHECKS=false"

echo "$DOCKER_ARGS" > /workspace/docker_args

echo "Generated Docker build args from Secret Manager"

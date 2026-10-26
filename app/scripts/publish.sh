#!/bin/bash
#
# publish.sh -- build the image and push it to Docker Hub.
#
#   app/scripts/publish.sh
#
# Required in the environment -- Docker Hub credentials, and nothing else:
#
#   GWS_DOCKERHUB_USERNAME   GWS_DOCKERHUB_TOKEN
#
# Pushes gbdconsult/gbd-geoservices:<version> (app/lib/version.py) and the
# moving :0.3. Not :latest, which belongs to an older image in the same
# repository.
#
# No deploy needs this: deploy.sh builds on the server. Built for
# linux/amd64, the servers' architecture, whatever machine this runs on --
# on an arm64 Mac that build is emulated and slow.

set -euo pipefail

IMAGE_REPO=gbdconsult/gbd-geoservices
MOVING_TAG=0.3
PLATFORM=linux/amd64

if [ $# -ne 0 ]; then
    echo "usage: $0     (no arguments)" >&2
    exit 2
fi

REPO=$(realpath "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/../..")

missing=()
for var in GWS_DOCKERHUB_USERNAME GWS_DOCKERHUB_TOKEN; do
    [ -n "${!var:-}" ] || missing+=("$var")
done
if [ "${#missing[@]}" -gt 0 ]; then
    echo "error: not set in the environment: ${missing[*]}" >&2
    exit 1
fi

VERSION=$(sed -n "s/^__version__ = ['\"]\(.*\)['\"]$/\1/p" "$REPO/app/lib/version.py")
if [ -z "$VERSION" ]; then
    echo "error: could not read __version__ from app/lib/version.py" >&2
    exit 1
fi
# What /status reports as `build`. -dirty: built from uncommitted code.
BUILD_ID=$(git -C "$REPO" rev-parse --short HEAD)
if [ -n "$(git -C "$REPO" status --porcelain)" ]; then
    BUILD_ID="$BUILD_ID-dirty"
fi

step() { echo; echo "==> $*"; }

step "Building $IMAGE_REPO:$VERSION ($BUILD_ID) for $PLATFORM"
docker build \
    --platform "$PLATFORM" \
    --build-arg "GBD_BUILD_ID=$BUILD_ID" \
    --tag "$IMAGE_REPO:$VERSION" \
    --tag "$IMAGE_REPO:$MOVING_TAG" \
    "$REPO"

step "Pushing to Docker Hub"
echo "$GWS_DOCKERHUB_TOKEN" | docker login --username "$GWS_DOCKERHUB_USERNAME" --password-stdin
docker push "$IMAGE_REPO:$VERSION"
docker push "$IMAGE_REPO:$MOVING_TAG"

echo
echo "==> Published $IMAGE_REPO:$VERSION and :$MOVING_TAG ($BUILD_ID)."

# One image for the whole stack, and a second one built from it for
# `manage.sh key-add` (the `keys` target below). app/ is bind-mounted over /app
# in the local compose file, so an edit on the host takes effect without a rebuild.

FROM python:3.12-bookworm AS app

# postgresql-client: psql for the operator.
# fonts-noto-core: Noto Sans, the only face the styles name; a style naming an absent
# face must fail at generation, which it cannot do if the font is missing from
# the image for a different reason.
# gdal-bin: gdalbuildvrt, gdalwarp and gdal_contour for `manage.py init-elevation`
# (importer/elevation.py); the Mapnik wheel's own GDAL has no command line tools.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client fonts-noto-core gdal-bin \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# PYTHONPATH=/app, so the directories under app/ are top-level packages
# (`import lib.text`, `import importer.run`) and `app` itself is never
# imported. No database setting here: the credentials are the deployment's
# config/postgres.env, which compose passes into the environment, and
# lib.config hands them to libpq when it loads -- so the image holds no
# credential.
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/ /app/

# The commit this image was built from, reported as `build` by /status --
# which tells a restarted server from one still on the previous image. `dev` when built without the argument.
ARG GBD_BUILD_ID=dev
ENV GEOSERVICES_BUILD_ID=$GBD_BUILD_ID

# One worker per container: the Map-object pool and the response cache are
# per-process, so a second worker doubles the memory and halves the cache hit
# rate. Concurrency comes from `map_pool_size` and from running more
# containers, not from more workers here.
EXPOSE 8000
# --no-access-log: uvicorn's own access logger writes the raw request line,
# `?key=...` and all, and no middleware can reach it. `web.main.access_log`
# logs every request already, with the key stripped.
CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

# The app plus the Bitwarden CLI, for the one-off `keys` service: `manage.py
# key-add` generates a key with scripts/vaultwarden-send.sh, which hands it
# over as a Vaultwarden Send, and registers it, all in one container that is
# gone afterwards. A target of its own, so the serving image has no vault
# tooling. The open-source build, pinned with GitHub's digests; a new version
# needs both digests from its release.
FROM app AS keys
ARG TARGETARCH
RUN case "${TARGETARCH:-amd64}" in \
        amd64) zip=bw-oss-linux-2026.9.1.zip \
               sum=b90c0fc86bcf11c0b194aa3f0a89344738af0512cb267c39ad3250c5edd71663 ;; \
        arm64) zip=bw-oss-linux-arm64-2026.9.1.zip \
               sum=6c2765f91d5bbba9864195c9a304a683bcc0bfa39cfd85ce9423142631e111a6 ;; \
        *) echo "no Bitwarden CLI build for $TARGETARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL -o /tmp/bw.zip "https://github.com/bitwarden/clients/releases/download/cli-v2026.9.1/$zip" \
    && echo "$sum  /tmp/bw.zip" | sha256sum -c - \
    && python -c 'import zipfile; zipfile.ZipFile("/tmp/bw.zip").extract("bw", "/usr/local/bin")' \
    && chmod 755 /usr/local/bin/bw \
    && rm /tmp/bw.zip

# The default target stays the app: every `docker build` and `build: .` without
# a --target gets the serving image, never the one with bw.
FROM app

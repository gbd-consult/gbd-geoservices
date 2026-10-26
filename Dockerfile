# One image for the whole stack. app/ is bind-mounted over /app in the local
# compose file, so an edit on the host takes effect without a rebuild.

FROM python:3.12-bookworm

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

"""Which `.osm.pbf` an area means, and getting hold of it.

The areas are the `areas` option: a name, which also names the area's
schemas, and the extract's path under `geofabrik_base`. A deployment adds one in its
options file.

This lives in the importer rather than in `manage.py` because `manage.py`
never touches the database or the filesystem itself -- it sequences module
functions, and this is one.
"""

from __future__ import annotations

import logging
import os
import re
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen, urlretrieve

from lib import config

log = logging.getLogger('importer')

def areas() -> dict[str, str]:
    """Area name -> path under `geofabrik_base`, from the `areas` option."""
    return config.opt('areas') or {}


def check(area: str) -> None:
    """Reject an unknown area by name, with the valid ones.

    A typo here otherwise surfaces much later as an empty schema. The name
    is also a schema name and a path segment under data_dir, and it comes
    from an options file, so it is held to a plain identifier.
    """
    known = areas()
    if area not in known:
        raise ValueError(f'unknown area {area!r}; choose from {", ".join(sorted(known))}')
    if not re.fullmatch(r'[a-z][a-z0-9_]*', area):
        raise ValueError(f'area name {area!r} in the areas option: lowercase letters, '
                         'digits and _ only, starting with a letter')


def url_for(area: str) -> str:
    check(area)
    base = config.opt('geofabrik_base', 'https://download.geofabrik.de/')
    return base.rstrip('/') + '/' + areas()[area]


def path_for(area: str, downloads: Path) -> Path:
    check(area)
    return Path(downloads) / Path(areas()[area]).name


def downloads_dir() -> Path:
    return Path(config.opt('data_dir', '/data')) / 'downloads'


def ensure(area: str, downloads: Path | None = None) -> Path:
    """The extract for `area`, downloaded again only when Geofabrik has a newer one.

    A `de` extract is several gigabytes, so a repeated run must not fetch it
    again; but `manage.sh update` runs the same import three times a week,
    and reusing the first download for ever leaves the data as old as it
    (`/health/data` caught that). So the file carries the server's
    Last-Modified as its mtime and a HEAD request compares the two. If the
    server cannot say, the file here is used, with a warning.

    Downloaded beside the target and renamed at the end, so an interrupted
    download is never taken for an extract.
    """
    downloads = downloads_dir() if downloads is None else Path(downloads)
    extract = path_for(area, downloads)
    url = url_for(area)
    remote = last_modified(url)
    if extract.exists() and (remote is None or extract.stat().st_mtime >= remote):
        log.info('reusing %s (%s)', extract,
                 'Geofabrik has no newer one' if remote else 'Geofabrik did not say how new')
        return extract

    log.info('downloading %s -> %s', url, extract)
    extract.parent.mkdir(parents=True, exist_ok=True)
    partial = extract.with_name(extract.name + '.part')
    urlretrieve(url, partial)  # noqa: S310 - the URL is built from the options
    if remote is not None:
        os.utime(partial, (remote, remote))
    partial.replace(extract)
    return extract


def last_modified(url: str) -> float | None:
    """The server's Last-Modified for `url` as a timestamp, or None."""
    try:
        with urlopen(Request(url, method='HEAD'), timeout=30) as response:  # noqa: S310
            return parsedate_to_datetime(response.headers['Last-Modified']).timestamp()
    except Exception as exc:                  # noqa: BLE001 - unreachable or no header: keep the file
        log.warning('no Last-Modified for %s: %s', url, exc)
        return None

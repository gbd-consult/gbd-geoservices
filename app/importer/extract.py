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
import re
from pathlib import Path
from urllib.request import urlretrieve

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
    """The extract for `area`, downloaded once and reused after that.

    A `de` extract is several gigabytes, so re-downloading it
    because a run was repeated is not a small mistake. Delete the file to
    force a fresh one.
    """
    downloads = downloads_dir() if downloads is None else Path(downloads)
    extract = path_for(area, downloads)
    if extract.exists():
        log.info('reusing %s (delete it to force a fresh download)', extract)
        return extract

    url = url_for(area)
    log.info('downloading %s -> %s', url, extract)
    extract.parent.mkdir(parents=True, exist_ok=True)
    urlretrieve(url, extract)  # noqa: S310 - the URL is built from the options
    return extract

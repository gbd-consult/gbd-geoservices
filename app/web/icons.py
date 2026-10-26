"""The category icons.

    GET /icons/{category}.svg

Every category has one (`styles/icons.yaml`, with inheritance resolved by
`manage.py compile-styles`), and every search result carries the URL of its own.
No key: an icon is styling, the same for every caller, and an `<img>` tag
cannot send the Authorization header.

Served from the icon set `current` names, in the default palette, with a
one-day cache: a changed icon reaches a browser within a day, and a result
list does not refetch a dozen small files per query.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from lib import config
from renderer import icons as icons_module
from web import httpcache

router = APIRouter(tags=['icons'])

MAX_AGE = 86400


@functools.lru_cache(maxsize=2)
def keys(icon_set: Path) -> dict[str, str]:
    """{category: icon key} of one icon set. A set never changes once written
    -- a changed one is a new directory -- so caching by path is safe."""
    return json.loads((icon_set / icons_module.KEYS).read_text())


def url(base: str, category: str) -> str:
    """The icon URL for a category, under the API's base URL."""
    return f'{base.rstrip("/")}/icons/{category}.svg'


@router.get('/icons/{category}.svg')
def icon(category: str) -> FileResponse:
    """The SVG of one category's icon."""
    # A category id, and nothing a path could be built from.
    if not re.fullmatch(r'cat(_[a-z0-9]+)+', category):
        raise HTTPException(status_code=404, detail='unknown category')
    icon_set = icons_module.current(Path(config.opt('data_dir', '/data')))
    if icon_set is None:
        raise HTTPException(status_code=404, detail='no icons: run manage.py compile-styles')
    icon_key = keys(icon_set).get(category)
    if icon_key is None:
        raise HTTPException(status_code=404, detail=f'unknown category {category!r}')
    path = icon_set / icons_module.DEFAULT_PALETTE / f'{icon_key}.svg'
    headers = ({'Cache-Control': f'public, max-age={MAX_AGE}'} if httpcache.enabled()
               else dict(httpcache.NO_STORE))
    return FileResponse(path, media_type='image/svg+xml', headers=headers)

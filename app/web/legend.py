"""The map legend.

    GET /legend/{theme}.png?lang=de

One PNG per theme and language, written by `manage.py compile-styles`
(`renderer/legend.py`); this only picks the file. The WMTS capabilities name
it as each layer's `LegendURL`, so QGIS and GWS show it without being told.

No key, as for `/icons`: a legend is styling, the same for every caller, and
a client that follows a `LegendURL` may not carry the key along.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from lib import db, i18n
from renderer import core
from web import httpcache, serving

router = APIRouter(tags=['legend'])

MAX_AGE = 86400


def url(base: str, theme: str) -> str:
    """The legend URL of a theme's URL name, under the API's base URL."""
    return f'{base.rstrip("/")}/legend/{theme}.png'


@router.get('/legend/{theme}.png')
def legend(theme: str, lang: str | None = None) -> FileResponse:
    """The legend of one theme, in `lang` or the default language."""
    schema = db.active_schema()
    name = serving.check_theme(theme, schema)
    path = core.styles_dir(schema) / 'legend' / f'{name}.{i18n.pick(lang)}.png'
    if not path.is_file():
        raise HTTPException(status_code=404, detail='no legend: run manage.py compile-styles')
    headers = ({'Cache-Control': f'public, max-age={MAX_AGE}'} if httpcache.enabled()
               else dict(httpcache.NO_STORE))
    return FileResponse(path, media_type='image/png', headers=headers)

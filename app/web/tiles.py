"""The XYZ tile route.

    GET /xyz/{theme}/{z}/{x}/{y}.{png,jpg}

`/xyz` is the EPSG:3857 case of `/wmts`, and says so in one place: both call
`serving.serve`, which is the whole of "look in the cache, else render, then
answer a conditional request". What differs is only how a URL becomes a
(set, level, col, row), and for XYZ that is the identity -- z/x/y *are*
level/col/row of the Web Mercator quadtree.

The handlers are deliberately `def` and not `async def`. A Mapnik render is
blocking C++ that holds the interpreter for tens of milliseconds; on the
event loop it would stall every other request for that time. FastAPI runs a
synchronous handler in a worker thread, which is what makes `map_pool_size`
concurrent renders actually concurrent.

The themes a client can ask for are listed by `/metadata` (`web/meta.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from lib import db
from web import auth, serving

router = APIRouter(tags=['tiles'], dependencies=[Depends(auth.requires('tiles'))])

#: The CRS of the grid `/xyz` is fixed to. Looked up by CRS rather than by
#: identifier, because the identifier is a key of `styles/grids.yaml` and
#: may be named differently.
XYZ_CRS = 'EPSG:3857'


def web_mercator():
    """The Web Mercator TileMatrixSet, or 404.

    A deployment that does not configure EPSG:3857 has no `/xyz` at all --
    which is legitimate (a UTM-only service) and is an address that does
    not exist rather than an error.
    """
    from fastapi import HTTPException

    from renderer import matrix

    tms = matrix.by_crs(matrix.load(), XYZ_CRS)
    if tms is None:
        raise HTTPException(status_code=404,
                            detail=f'{XYZ_CRS} is not configured on this server')
    return tms


# GET *and* HEAD. FastAPI's `.get()` registers only GET, unlike Starlette's
# plain routes which add HEAD alongside it -- so `curl -I` on a tile, and
# every monitor that probes with HEAD, got a 405. Starlette drops the body
# for a HEAD response itself, so the handler is the same one.
@router.api_route('/xyz/{theme}/{z}/{x}/{y}.{fmt}', methods=['GET', 'HEAD'])
def xyz(request: Request, theme: str, z: int, x: int, y: int, fmt: str) -> Response:
    """One raster tile in EPSG:3857.

    `theme` is the URL name (`serving.url_name`) -- `std`, `max`, `dark`,
    `dark_min`. Validated against the compiled XML on disk rather than
    against a list in code, so a theme that was never generated is a 404
    instead of a render that fails deep inside Mapnik.
    """
    schema = db.active_schema()
    fmt = serving.check_format(fmt)
    theme = serving.check_theme(theme, schema)
    return serving.serve(request, theme=theme, tms=web_mercator(),
                         level=z, col=x, row=y, fmt=fmt, schema=schema)

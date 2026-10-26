"""WMTS: GetCapabilities and GetTile, in both the RESTful and KVP forms.

    GET /wmts?SERVICE=WMTS&REQUEST=GetCapabilities
    GET /wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=<theme>
        &TILEMATRIXSET=<set>&TILEMATRIX=<level>&TILEROW=<row>&TILECOL=<col>
        &FORMAT=image/png
    GET /wmts/{theme}/{set}/{level}/{col}/{row}.{fmt}

Three things follow from the renderer:

- **the advertised sets are computed** from `styles/grids.yaml` through
  `renderer.matrix`, so what is advertised and what is served cannot drift.
- **an unconfigured CRS is a 404**, not an on-demand render in a projection
  nothing was compiled for.
- **the ResourceURLs carry the key through.** QGIS is the client that
  matters most here and `?key=` is the only carrier it can send, so a
  capabilities document fetched with a key advertises tile URLs that have
  it -- otherwise every layer a user adds from it is unauthorised.
- **each layer's style names its legend** (`LegendURL`, `web/legend.py`),
  in the language of `?lang=` when the capabilities were asked for one.

Per the OGC spec, KVP parameter *names* are case-insensitive, so `layer=`
and `LAYER=` both work. The *values* are not: a theme is a filename.
A layer is a theme's URL name (`serving.url_name`), as in `/xyz`.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from lib import config, db, i18n
from web import auth, formats, meta, serving
from web import legend as legend_routes

router = APIRouter(tags=['wmts'], dependencies=[Depends(auth.requires('tiles'))])

OWS_NS = 'http://www.opengis.net/ows/1.1'
WMTS_NS = 'http://www.opengis.net/wmts/1.0'
XLINK_NS = 'http://www.w3.org/1999/xlink'

ET.register_namespace('', WMTS_NS)
ET.register_namespace('ows', OWS_NS)
ET.register_namespace('xlink', XLINK_NS)


def ci_params(request: Request) -> dict[str, str]:
    """Query parameters with lower-cased *names*.

    The spec says names are case-insensitive; values are not, and a theme
    name is a filename, so only the keys are folded.
    """
    return {name.lower(): value for name, value in request.query_params.items()}


@router.get('/wmts')
def wmts_kvp(request: Request) -> Response:
    """The KVP binding: one endpoint, `REQUEST` decides."""
    params = ci_params(request)
    operation = (params.get('request') or '').lower()

    if operation == 'getcapabilities':
        return capabilities_response(request)
    if operation == 'gettile':
        return kvp_get_tile(request, params)
    raise HTTPException(
        status_code=400,
        detail="REQUEST must be GetCapabilities or GetTile")


def kvp_get_tile(request: Request, params: dict[str, str]) -> Response:
    """GetTile from KVP parameters, onto the same path the RESTful form takes."""
    missing = [name for name in ('layer', 'tilematrix', 'tilerow', 'tilecol')
               if not params.get(name)]
    if missing:
        raise HTTPException(status_code=400,
                            detail=f'missing parameter(s): {", ".join(missing).upper()}')

    try:
        level = int(params['tilematrix'])
        row = int(params['tilerow'])
        col = int(params['tilecol'])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail='TILEMATRIX, TILEROW and TILECOL must be whole numbers') from None

    # FORMAT is optional and defaults to PNG: several clients omit it, and
    # refusing them over a parameter with one sensible answer helps nobody.
    return get_tile(request, theme=params['layer'],
                    matrix_set=params.get('tilematrixset') or default_set(),
                    level=level, col=col, row=row,
                    fmt=params.get('format') or 'image/png')


@router.api_route('/wmts/{theme}/{matrix_set}/{level}/{col}/{row}.{fmt}',
                  methods=['GET', 'HEAD'])
def wmts_rest(request: Request, theme: str, matrix_set: str,
              level: int, col: int, row: int, fmt: str) -> Response:
    """The RESTful binding, which is what the ResourceURL template names."""
    return get_tile(request, theme=theme, matrix_set=matrix_set,
                    level=level, col=col, row=row, fmt=fmt)


def get_tile(request: Request, *, theme: str, matrix_set: str,
             level: int, col: int, row: int, fmt: str) -> Response:
    schema = db.active_schema()
    canonical = serving.check_format(fmt)
    theme = serving.check_theme(theme, schema)
    tms = matrix_set_by_identifier(matrix_set)
    return serving.serve(request, theme=theme, tms=tms, level=level, col=col,
                         row=row, fmt=canonical, schema=schema)


def matrix_sets() -> dict:
    """The served sets, by the identifier a request sends."""
    from renderer import matrix

    return matrix.load()


def default_set() -> str:
    """What `TILEMATRIXSET` defaults to when a client omits it.

    Web Mercator when it is configured, because that is what a client that
    did not think about it means; otherwise the first configured set, so a
    UTM-only deployment still answers.
    """
    from renderer import matrix

    sets = matrix.load()
    web = matrix.by_crs(sets, 'EPSG:3857')
    if web is not None:
        return web.identifier
    return sorted(sets)[0]


def matrix_set_by_identifier(identifier: str):
    sets = matrix_sets()
    if identifier not in sets:
        # 404, not an on-demand render in a projection nothing was
        # compiled for.
        raise HTTPException(
            status_code=404,
            detail=f'unknown TileMatrixSet {identifier!r}; '
                   f'this server serves {", ".join(sorted(sets))}')
    return sets[identifier]


# --- GetCapabilities -----------------------------------------------------

def capabilities_response(request: Request) -> Response:
    schema = db.active_schema()
    from renderer import core

    # Only a language asked for, and only a served one: the legend route
    # picks the default itself.
    lang = ci_params(request).get('lang')
    document = build_capabilities(
        themes=[serving.url_name(theme) for theme in core.available_themes(schema)],
        sets=matrix_sets(),
        base_url=base_url(request),
        key=auth.presented(request),
        lang=i18n.pick(lang) if lang else None,
        contours=meta.has_contours(schema),
    )
    return Response(content=document, media_type='application/xml')


def base_url(request: Request) -> str:
    """The absolute URL this server is reached at, without a trailing slash.

    From the request rather than from configuration, so a deployment behind
    a proxy on another host advertises URLs that work -- provided the proxy
    sets X-Forwarded-*, which uvicorn turns into the request's scheme and
    host when run with --proxy-headers.
    """
    return str(request.base_url).rstrip('/')


def build_capabilities(*, themes, sets: dict, base_url: str,
                       key: str | None = None, lang: str | None = None,
                       contours: bool = False) -> bytes:
    """The capabilities document: one Layer per theme, one TileMatrixSet each.

    Every theme advertises every raster format and every configured set,
    which is true here because the generator writes every theme for every
    set or fails before writing anything.
    """
    capabilities = ET.Element(f'{{{WMTS_NS}}}Capabilities', {'version': '1.0.0'})

    identification = ET.SubElement(capabilities, f'{{{OWS_NS}}}ServiceIdentification')
    ET.SubElement(identification, f'{{{OWS_NS}}}Title').text = 'gbd-geoservices'
    ET.SubElement(identification, f'{{{OWS_NS}}}ServiceType').text = 'OGC WMTS'
    ET.SubElement(identification, f'{{{OWS_NS}}}ServiceTypeVersion').text = '1.0.0'
    ET.SubElement(identification, f'{{{OWS_NS}}}Fees').text = 'none'
    ET.SubElement(identification, f'{{{OWS_NS}}}AccessConstraints').text = (
        'Map data (c) OpenStreetMap contributors, ODbL'
        + (f'; elevation {meta.ELEVATION_ATTRIBUTION}' if contours else ''))

    contents = ET.SubElement(capabilities, f'{{{WMTS_NS}}}Contents')

    suffix = f'?key={key}' if key else ''
    for theme in themes:
        append_layer(
            contents,
            identifier=theme,
            formats_=formats.RASTER,
            set_ids=sorted(sets),
            href_template=(f'{base_url}/wmts/{theme}/{{TileMatrixSet}}/'
                           f'{{TileMatrix}}/{{TileCol}}/{{TileRow}}'),
            suffix=suffix,
            legend_url=legend_routes.url(base_url, theme) + (f'?lang={lang}' if lang else ''),
        )

    for identifier, tms in sorted(sets.items()):
        append_matrix_set(contents, identifier, tms)

    ET.SubElement(capabilities, f'{{{OWS_NS}}}ServiceMetadataURL').set(
        f'{{{XLINK_NS}}}href', f'{base_url}/wmts?SERVICE=WMTS&REQUEST=GetCapabilities')
    capabilities.set('{http://www.w3.org/XML/1998/namespace}lang',
                     str(config.opt('lang', 'de')))
    return ET.tostring(capabilities, encoding='utf-8', xml_declaration=True)


def append_layer(contents, *, identifier: str, formats_, set_ids, href_template: str,
                 suffix: str = '', legend_url: str | None = None) -> None:
    layer = ET.SubElement(contents, f'{{{WMTS_NS}}}Layer')
    ET.SubElement(layer, f'{{{OWS_NS}}}Title').text = identifier
    ET.SubElement(layer, f'{{{OWS_NS}}}Identifier').text = identifier
    # A Layer must carry a WGS84 bounding box; the pyramid is global even
    # where the data is not, and advertising the imported extent would make
    # a client refuse to request the empty tiles it is entitled to.
    bbox = ET.SubElement(layer, f'{{{OWS_NS}}}WGS84BoundingBox')
    ET.SubElement(bbox, f'{{{OWS_NS}}}LowerCorner').text = '-180 -85.051129'
    ET.SubElement(bbox, f'{{{OWS_NS}}}UpperCorner').text = '180 85.051129'
    style = ET.SubElement(layer, f'{{{WMTS_NS}}}Style', {'isDefault': 'true'})
    ET.SubElement(style, f'{{{OWS_NS}}}Identifier').text = 'default'
    if legend_url:
        # No key: `/legend` takes none, like `/icons`.
        ET.SubElement(style, f'{{{WMTS_NS}}}LegendURL', {
            'format': 'image/png', f'{{{XLINK_NS}}}href': legend_url})

    for fmt in formats_:
        ET.SubElement(layer, f'{{{WMTS_NS}}}Format').text = formats.mime_for(fmt)

    for set_id in set_ids:
        link = ET.SubElement(layer, f'{{{WMTS_NS}}}TileMatrixSetLink')
        ET.SubElement(link, f'{{{WMTS_NS}}}TileMatrixSet').text = set_id

    for fmt in formats_:
        resource = ET.SubElement(layer, f'{{{WMTS_NS}}}ResourceURL')
        resource.set('format', formats.mime_for(fmt))
        resource.set('resourceType', 'tile')
        resource.set('template', f'{href_template}.{fmt}{suffix}')


def append_matrix_set(contents, identifier: str, tms) -> None:
    element = ET.SubElement(contents, f'{{{WMTS_NS}}}TileMatrixSet')
    ET.SubElement(element, f'{{{OWS_NS}}}Identifier').text = identifier
    ET.SubElement(element, f'{{{OWS_NS}}}SupportedCRS').text = tms.crs

    for level in sorted(tms.matrices, key=int):
        matrix = tms.matrices[level]
        matrix_el = ET.SubElement(element, f'{{{WMTS_NS}}}TileMatrix')
        ET.SubElement(matrix_el, f'{{{OWS_NS}}}Identifier').text = matrix.identifier
        ET.SubElement(matrix_el, f'{{{WMTS_NS}}}ScaleDenominator').text = repr(
            matrix.scale_denominator)
        ET.SubElement(matrix_el, f'{{{WMTS_NS}}}TopLeftCorner').text = (
            f'{matrix.top_left[0]} {matrix.top_left[1]}')
        ET.SubElement(matrix_el, f'{{{WMTS_NS}}}TileWidth').text = str(matrix.tile_width)
        ET.SubElement(matrix_el, f'{{{WMTS_NS}}}TileHeight').text = str(matrix.tile_height)
        ET.SubElement(matrix_el, f'{{{WMTS_NS}}}MatrixWidth').text = str(matrix.matrix_width)
        ET.SubElement(matrix_el, f'{{{WMTS_NS}}}MatrixHeight').text = str(matrix.matrix_height)



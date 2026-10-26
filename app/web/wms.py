"""WMS 1.3.0 (and 1.1.1 requests): GetCapabilities and GetMap.

    GET /wms?SERVICE=WMS&REQUEST=GetCapabilities
    GET /wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=<theme>&STYLES=
        &CRS=EPSG:25832&BBOX=<minx,miny,maxx,maxy>&WIDTH=<px>&HEIGHT=<px>
        &FORMAT=image/png

A GetMap is a render of the requested bbox at the requested size, not a
mosaic of tiles, and it is not cached: an arbitrary bbox has no tile address.
`wms_max_px` caps each side.

- **a CRS renders with the compiled XML of its grid**, because the scale
  arithmetic is baked in per grid (`renderer/styles.py`): EPSG:3857 with
  `GoogleMapsCompatible`, EPSG:25832/25833 with `DE_EPSG_25832_ADV`/`DE_EPSG_25833_ADV`, and only
  when that grid is served. EPSG:4326 uses the Web Mercator file too: Mapnik
  turns a geographic scale into metres with the equator's metres per degree,
  which is the unit the Web Mercator `minzoom` columns are written in.
- **EPSG:4326 in 1.3.0 is lat/lon.** BBOX is then miny,minx,maxy,maxx; in
  1.1.1 (`SRS=`) it is lon/lat as for every other CRS.
- **the OnlineResources carry the key through**, as the WMTS ResourceURLs do
  (`web/wmts.py`): QGIS can only send `?key=`.

Parameter names are case-insensitive, values are not (`wmts.ci_params`).
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from lib import config, db, i18n, timing
from web import auth, formats, httpcache, meta, serving
from web import legend as legend_routes
from web.wmts import base_url, ci_params

log = logging.getLogger(__name__)

router = APIRouter(tags=['wms'], dependencies=[Depends(auth.requires('tiles'))])

WMS_NS = 'http://www.opengis.net/wms'
XLINK_NS = 'http://www.w3.org/1999/xlink'

#: Rendered with the Web Mercator file and its scale arithmetic.
GEOGRAPHIC = 'EPSG:4326'
WEB_MERCATOR = 'EPSG:3857'


@router.get('/wms')
def wms_kvp(request: Request) -> Response:
    params = ci_params(request)
    operation = (params.get('request') or '').lower()
    if operation == 'getcapabilities':
        return capabilities_response(request)
    if operation == 'getmap':
        return get_map(request, params)
    raise HTTPException(status_code=400,
                        detail='REQUEST must be GetCapabilities or GetMap')


def served_crs() -> dict:
    """{CRS: the TileMatrixSet whose compiled XML renders it}."""
    from renderer import matrix

    sets = matrix.load().values()
    out = {tms.crs.upper(): tms for tms in sets}
    if WEB_MERCATOR in out:
        out[GEOGRAPHIC] = out[WEB_MERCATOR]
    return out


def max_px() -> int:
    return int(config.opt('wms_max_px', 4096))


def get_map(request: Request, params: dict[str, str]) -> Response:
    from renderer import core

    crs_param = 'srs' if (params.get('version') or '').startswith('1.1') else 'crs'
    missing = [name for name in ('layers', crs_param, 'bbox', 'width', 'height')
               if not params.get(name)]
    if missing:
        raise HTTPException(status_code=400,
                            detail=f'missing parameter(s): {", ".join(missing).upper()}')

    layers = params['layers'].split(',')
    if len(layers) != 1:
        raise HTTPException(status_code=400, detail='LAYERS must name exactly one layer')

    crs = params[crs_param].upper()
    sets = served_crs()
    if crs not in sets:
        raise HTTPException(status_code=400,
                            detail=f'unsupported CRS {crs!r}; this server serves '
                                   f'{", ".join(sorted(sets))}')

    try:
        bbox = tuple(float(v) for v in params['bbox'].split(','))
        width, height = int(params['width']), int(params['height'])
    except ValueError:
        raise HTTPException(status_code=400,
                            detail='BBOX must be four numbers, WIDTH and HEIGHT whole numbers') from None
    if len(bbox) != 4 or not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        raise HTTPException(status_code=400, detail='BBOX must be minx,miny,maxx,maxy')
    if not (0 < width <= max_px() and 0 < height <= max_px()):
        raise HTTPException(status_code=400,
                            detail=f'WIDTH and HEIGHT must be between 1 and {max_px()}')
    if crs == GEOGRAPHIC and crs_param == 'crs':
        bbox = (bbox[1], bbox[0], bbox[3], bbox[2])     # 1.3.0: lat/lon

    schema = db.active_schema()
    fmt = serving.check_format(params.get('format') or 'image/png')
    theme = serving.check_theme(layers[0], schema)
    tms = sets[crs]

    steps = timing.Steps()
    try:
        data = core.render_tile(theme, bbox, fmt, crs, tms.identifier, steps=steps,
                                size=(width, height))
    except Exception as exc:                  # noqa: BLE001
        log.exception('WMS render failed for %s %s %s', theme, crs, bbox)
        raise HTTPException(status_code=500, detail='map render failed') from exc
    timing.report(log, steps, f'wms {theme} {crs} {width}x{height}')

    headers = httpcache.headers(httpcache.tile_etag(data), versioned=False)
    return Response(content=data, media_type=formats.mime_for(fmt), headers=headers)


# --- GetCapabilities -----------------------------------------------------

def capabilities_response(request: Request) -> Response:
    from renderer import core

    schema = db.active_schema()
    lang = ci_params(request).get('lang')
    document = build_capabilities(
        themes=[serving.url_name(theme) for theme in core.available_themes(schema)],
        crs=sorted(served_crs()),
        base_url=base_url(request),
        key=auth.presented(request),
        lang=i18n.pick(lang) if lang else None,
        attribution=meta.attribution(schema),
    )
    return Response(content=document, media_type='text/xml')


def build_capabilities(*, themes, crs, base_url: str, key: str | None = None,
                       lang: str | None = None, attribution: str = meta.ATTRIBUTION) -> bytes:
    """One root Layer with every served CRS, one child Layer per theme.

    Element names are written unqualified with the namespaces as plain
    attributes: `ET.register_namespace` is process-wide, and claiming the
    default prefix for WMS would take it from the WMTS document.
    """
    def sub(parent, tag, text=None, **attrs):
        element = ET.SubElement(parent, tag, attrs)
        if text is not None:
            element.text = text
        return element

    def online(parent, href):
        return sub(parent, 'OnlineResource', **{'xlink:type': 'simple', 'xlink:href': href})

    endpoint = f'{base_url}/wms' + (f'?key={key}' if key else '')

    root = ET.Element('WMS_Capabilities', {
        'version': '1.3.0', 'xmlns': WMS_NS, 'xmlns:xlink': XLINK_NS})

    service = sub(root, 'Service')
    sub(service, 'Name', 'WMS')
    sub(service, 'Title', 'gbd-geoservices')
    online(service, f'{base_url}/wms')
    sub(service, 'Fees', 'none')
    sub(service, 'AccessConstraints', f'Map data {attribution}')
    sub(service, 'LayerLimit', '1')
    sub(service, 'MaxWidth', str(max_px()))
    sub(service, 'MaxHeight', str(max_px()))

    capability = sub(root, 'Capability')
    request = sub(capability, 'Request')
    for operation, mimes in (('GetCapabilities', ['text/xml']),
                             ('GetMap', [formats.mime_for(f) for f in formats.RASTER])):
        element = sub(request, operation)
        for mime in mimes:
            sub(element, 'Format', mime)
        online(sub(sub(sub(element, 'DCPType'), 'HTTP'), 'Get'), endpoint)
    # Errors are the API's JSON, not a ServiceExceptionReport.
    sub(sub(capability, 'Exception'), 'Format', 'application/json')

    top = sub(capability, 'Layer')
    sub(top, 'Title', 'gbd-geoservices')
    for name in crs:
        sub(top, 'CRS', name)
    # Global, as in the WMTS capabilities: the data's extent would make a
    # client refuse the empty maps it is entitled to.
    box = sub(top, 'EX_GeographicBoundingBox')
    sub(box, 'westBoundLongitude', '-180')
    sub(box, 'eastBoundLongitude', '180')
    sub(box, 'southBoundLatitude', '-85.051129')
    sub(box, 'northBoundLatitude', '85.051129')

    for theme in themes:
        layer = sub(top, 'Layer', queryable='0')
        sub(layer, 'Name', theme)
        sub(layer, 'Title', theme)
        style = sub(layer, 'Style')
        sub(style, 'Name', 'default')
        sub(style, 'Title', 'default')
        legend = sub(style, 'LegendURL')
        sub(legend, 'Format', 'image/png')
        # No key: `/legend` takes none.
        online(legend, legend_routes.url(base_url, theme) + (f'?lang={lang}' if lang else ''))

    root.set('xml:lang', str(config.opt('lang', 'de')))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

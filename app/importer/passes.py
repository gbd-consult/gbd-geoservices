"""The osmium passes: a file in, render rows out.

Four passes. A relation pre-pass first, because nothing inside the others
can know which ways a boundary relation is made of, and then nodes, ways
and areas in separate processes (DESIGN.md "Import").

What the split actually costs, measured against the library rather than
guessed: `with_locations()` refuses to run unless nodes are read from the
file, so the ways and areas passes each scan every node anyway to fill
their own location store, and `with_areas()` additionally reads ways and
relations. The split therefore pays about two extra node scans and two
extra location stores. What it buys is the per-object Python work -- the
classification, the projection, the row building, which is the bulk of the
import -- running on three cores instead of one, when memory allows it
(`run`'s `pass_workers`).

Filters do not starve the location cache: pyosmium installs the location
handler ahead of the filter chain, so a way whose nodes never reached
Python still gets its geometry. That is what lets the ways pass drop nodes
with an EntityFilter while keeping every way, tagged or not -- and it has
to keep untagged ways, because a boundary relation's members usually carry
no tags of their own.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import osmium

from importer import features
from importer import geometry as geom
from importer import params as params_module
from importer import rules as rules_module
from importer import tables as t
from importer.progress import Progress
from importer.writer import TableWriter
from lib import db

E = osmium.osm

#: Keys the importer reads directly, which no rule mentions: without them a
#: KeyFilter built from the classifier alone would drop every object whose
#: only tags are an address or a name -- 62 257 addresses on Schleswig-
#: Holstein, 8.6 % of the total.
ATTRIBUTE_KEYS = frozenset({
    'name', 'addr:housenumber', 'addr:street', 'addr:postcode', 'addr:city',
    'height', 'building:levels', 'layer', 'population', 'ref', 'ele',
    'maritime', 'area',
})

#: Tags that make a closed way an area rather than a ring-shaped line.
AREA_LIKE_KEYS = frozenset({
    'building', 'landuse', 'amenity', 'leisure', 'natural', 'water',
    'waterway', 'aeroway', 'tourism', 'place', 'boundary', 'military',
    'man_made',
})

#: The class whose polygons go to osm_building rather than osm_polygon.
BUILDING_CLASS = 'cls_building'

#: German admin levels that have a render class. Others are dropped.
ADMIN_LEVELS = (2, 4, 6, 8)


def admin_classes(classifier) -> frozenset[str]:
    """The classes the synthetic boundary tags produce.

    Asked of the classifier rather than spelled out, so a rename in
    `model/classifier.yaml` cannot leave a hardcoded name behind here.
    """
    return frozenset(
        classifier.classify(
            classifier.tag_bits({'boundary': 'administrative', 'admin_level': str(level)}),
            'line').cls
        for level in ADMIN_LEVELS)


def filter_keys(classifier) -> tuple[str, ...]:
    return tuple(sorted(classifier.relevant_keys | ATTRIBUTE_KEYS))


def way_is_closed(way) -> bool:
    if len(way.nodes) < 4:
        return False
    return way.nodes[0].ref == way.nodes[-1].ref


def tags_imply_area(tags) -> bool:
    area = tags.get('area')
    if area == 'yes':
        return True
    if area == 'no':
        return False
    if not any(key in tags for key in AREA_LIKE_KEYS):
        return False
    # A closed highway is a loop, not a plaza, unless it says otherwise.
    return not ('highway' in tags and area != 'yes')


# --- pass 0: relations ---------------------------------------------------

def boundary_levels(extract: Path, progress_s: float) -> dict[int, int]:
    """{way id: lowest admin_level of any administrative relation it bounds}.

    Every border way belongs to at least two municipalities and often to a
    district and a state as well; taking the lowest level is what draws it
    once, as the most important boundary it carries.
    """
    levels: dict[int, int] = {}
    progress = Progress('relations', progress_s)
    for relation in osmium.FileProcessor(extract, E.RELATION):
        progress.tick()
        if relation.tags.get('boundary') != 'administrative':
            continue
        try:
            level = int(relation.tags.get('admin_level', ''))
        except ValueError:
            continue
        if level not in ADMIN_LEVELS:
            continue
        progress.keep()
        for member in relation.members:
            if member.type == 'w' and member.role in ('outer', ''):
                current = levels.get(member.ref)
                if current is None or level < current:
                    levels[member.ref] = level
    progress.done()
    return levels


# --- the render sink -----------------------------------------------------

class RenderSink:
    """The render tables, plus the batching the geometry work needs.

    Objects are buffered raw and projected a batch at a time: shapely hands
    one array of coordinates to one callback, which is 2.6 us per geometry
    against 20 us calling it per geometry, and the projection has to happen
    before the row can be built because minzoom is computed from the
    projected size.
    """

    def __init__(self, conn, schema: str, params, batch: int):
        self._params = params
        self._batch = batch
        self._pending: list[tuple] = []
        self.writers = {
            'point': TableWriter(conn, schema, t.OSM_POINT, batch),
            'line': TableWriter(conn, schema, t.OSM_LINE, batch),
            'polygon': TableWriter(conn, schema, t.OSM_POLYGON, batch),
            'building': TableWriter(conn, schema, t.OSM_BUILDING, batch),
            'label': TableWriter(conn, schema, t.OSM_LABEL, batch),
            'search': TableWriter(conn, schema, t.OSM_SEARCH_OBJECT, batch),
            'address': TableWriter(conn, schema, t.OSM_SEARCH_ADDRESS, batch),
            'street_ends': TableWriter(conn, schema, t.STREET_ENDS, batch),
        }

    def add(self, osm_id: int, result, tags: dict, wkb: str, kind: str,
            ends: tuple[int, int] | None = None, *, search: bool = True) -> None:
        """`ends` marks a named street: its search row is the merged street,
        built in post-processing, so it goes to the merge input instead.

        `search=False` writes the render row and nothing else. It is for the
        one object that is written twice: a way that is both an
        administrative border and a feature of its own gets a border row
        *and* its own row, and the search side belongs to the feature -- a
        river named Stör is a river, not a district boundary.
        """
        self._pending.append((osm_id, result, tags, wkb, kind, ends, search))
        if len(self._pending) >= self._batch:
            self.flush()

    def flush(self) -> None:
        if not self._pending:
            return
        pending, self._pending = self._pending, []

        # One parse, two serialisations: the render tables take the projected
        # geometry, the search tables the 4326 one it was projected from.
        original = geom.from_wkb([item[3] for item in pending])
        projected = geom.to_3857(original)

        for (osm_id, result, tags, _wkb, kind, ends, search), geometry, plain in zip(
                pending, projected, original, strict=True):
            self._render(osm_id, result, tags, kind, geometry)
            if search:
                self._search(osm_id, result, tags, kind, plain, ends)

    def _search(self, osm_id, result, tags, kind, plain, ends) -> None:
        name = tags.get('name')
        housenumber = tags.get('addr:housenumber')
        if not (name or housenumber):
            return
        centre = geom.label_anchor(plain)
        if ends is not None:
            self.writers['street_ends'].add(
                features.street_ends_row(osm_id, result, tags, *ends))
        elif name and result.importance != 0:
            # Importance 0 is "never found", whatever the name. An object
            # without a category (None) is still found by its name.
            self.writers['search'].add(
                features.search_row(osm_id, result, self._params, tags, plain, kind, centre))
        if housenumber:
            self.writers['address'].add(
                features.address_row(osm_id, tags, centre, result.category))

    def _marker(self, osm_id, result, tags, anchor) -> None:
        """A point row for a POI that was mapped as an area or a way.

        `marker` mode reads osm_point; 53 of that layer's classes exist
        only in osm_polygon on a real import, so without this they get no
        dot. The anchor is already in hand -- it is the same
        point-on-surface the label uses.
        """
        if self._params.draws_marker(result.cls):
            self.writers['point'].add(
                features.marker_row(osm_id, result, self._params, tags, anchor))

    def _render(self, osm_id, result, tags, kind, geometry) -> None:
        """The render tables, from the projected geometry.

        An object with a name but no class -- a named boundary relation, an
        address node -- is searchable and not drawn, so it stops here.
        """
        params = self._params
        if result.cls is None:
            return

        if kind == 'polygon':
            if result.cls == BUILDING_CLASS:
                rows = features.building_rows(osm_id, result, params, tags, geometry)
                target = self.writers['building']
            else:
                rows = features.explode(osm_id, result, params, tags, geometry)
                target = self.writers['polygon']
            if not rows:
                return
            for row in rows:
                target.add(row)
            anchor = geom.label_anchor(geometry)
            self._marker(osm_id, result, tags, anchor)
            # Every part shares the non-geometry columns, so any of them
            # carries the zooms the single label row needs.
            label = features.label_row(rows[0], result, anchor)
        elif kind == 'line':
            self.writers['line'].add(
                features.render_row(osm_id, result, params, tags, geometry, kind))
            self._marker(osm_id, result, tags, geom.label_anchor(geometry))
            # No label row: a line's text is drawn from osm_line itself with
            # placement: line, which needs the line geometry.
            label = None
        else:
            row = features.point_row(osm_id, result, params, tags, geometry)
            self.writers['point'].add(row)
            label = features.label_row(row, result, geometry)

        if label is not None:
            self.writers['label'].add(label)

    def close(self) -> dict[str, int]:
        self.flush()
        return {name: writer.close() for name, writer in self.writers.items()}


def _is_relevant(tags, keys) -> bool:
    return any(key in tags for key in keys)


def line_dispatch(classifier, admin, tags, *, level, relevant, closed_area):
    """What one way writes to osm_line, as [(result, search)] in write order.

    Pulled out of the loop because this is the whole of the ways pass's
    judgement and it is worth testing without a pbf.

    Three shapes come out of it:

    * `[]` -- nothing to write.
    * `[(border, True)]` -- the way is a border and nothing else, or is
      itself tagged as one. Written **once**, at the lowest admin level any
      relation claims it at, so it is not duplicated: every border way
      belongs to at least two municipalities.
    * `[(border, False), (own, True)]` -- the way is a border *and* a
      feature. Measured on Schleswig-Holstein: 113 of them, 108 waterways
      and 5 coastline ways. Taking the border alone would erase the river, and
      with it five pieces of the coastline on the extract chosen for having
      one. The search row goes with the feature, not the border: a river
      named Stör is a river.
    """
    # A sea border must not cross the water (DESIGN.md "Import"). That is a
    # statement about the border, not about the way, so it suppresses an
    # administrative class from *either* source -- the relation's and the
    # way's own tags, which 63 of the 65 maritime ways on Schleswig-Holstein
    # also carry -- while leaving a coastline or a river on it alone.
    maritime = tags.get('maritime') == 'yes'

    own = None
    if relevant and not closed_area:
        candidate = classifier.classify(classifier.tag_bits(tags), 'line')
        if worth_keeping(candidate, tags) and not (maritime and candidate.cls in admin):
            own = candidate

    border = None
    if level is not None and not maritime:
        border = classifier.classify(
            classifier.tag_bits({'boundary': 'administrative',
                                 'admin_level': str(level)}), 'line')

    if border is None:
        return [(own, True)] if own is not None else []
    if own is None or own.cls is None or own.cls in admin:
        return [(border, True)]
    return [(border, False), (own, True)]


def drawn_as_line(classifier, bits: int, tags, result) -> bool:
    """Whether a closed way the area builder turned into an area is the line
    the ways pass already wrote.

    osmium builds an area from every closed way. A closed road -- a loop, a
    turning circle -- is a line to the ways pass (`tags_imply_area`), and as
    an area it has no class, so it would be a second object in search, filed
    as "other road": 697 of them on de_sh. An area that has a class of its own
    stays, and so does one the tags call an area.
    """
    return (not tags_imply_area(tags) and result.cls is None
            and classifier.classify(bits, 'line').cls is not None)


def worth_keeping(result, tags) -> bool:
    """Whether the object produces any row at all.

    Skipping an object that no rule gives a class or a category would drop
    every address-only and name-only object -- 62 257 addresses on de_sh, 8.6 % of them -- because no rule
    mentions an addr:* key or `name`, so they match nothing. The test is
    what the object would actually write: a render row, a search row, or an
    address row.
    """
    return bool(result.cls or tags.get('name') or tags.get('addr:housenumber'))


# --- the three passes ----------------------------------------------------

def _setup(model_dir: Path, styles_dir: Path):
    classifier = rules_module.load(model_dir)
    params = params_module.load(model_dir, styles_dir)
    return classifier, params, frozenset(filter_keys(classifier))


def run_nodes(extract: Path, schema: str, model_dir: Path, styles_dir: Path) -> dict[str, int]:
    classifier, params, keys = _setup(model_dir, styles_dir)
    wkb = osmium.geom.WKBFactory()
    processor = (osmium.FileProcessor(extract, E.NODE)
                 .with_filter(osmium.filter.EmptyTagFilter())
                 .with_filter(osmium.filter.KeyFilter(*sorted(keys))))

    with db.connection() as conn:
        sink = RenderSink(conn, schema, params, params.copy_batch)
        progress = Progress('nodes', params.progress_s)
        for node in processor:
            progress.tick()
            tags = dict(node.tags)
            result = classifier.classify(classifier.tag_bits(tags), 'point')
            if not worth_keeping(result, tags):
                continue
            progress.keep()
            sink.add(node.id, result, tags, wkb.create_point(node), 'point')
        counts = sink.close()
        progress.done()
        conn.commit()
    return counts


def run_ways(extract: Path, schema: str, model_dir: Path, styles_dir: Path,
             boundaries: dict[int, int]) -> dict[str, int]:
    """Lines only. Closed ways that are areas belong to the areas pass.

    No tag filter, because a boundary relation's member ways usually carry
    no tags and EmptyTagFilter would drop exactly the ones pass 0 found.
    The EntityFilter keeps nodes out of Python while still letting the
    location cache fill from them.
    """
    classifier, params, keys = _setup(model_dir, styles_dir)
    wkb = osmium.geom.WKBFactory()
    processor = (osmium.FileProcessor(extract, E.NODE | E.WAY)
                 .with_locations(params.location_store)
                 .with_filter(osmium.filter.EntityFilter(E.WAY)))

    admin = admin_classes(classifier)

    with db.connection() as conn:
        sink = RenderSink(conn, schema, params, params.copy_batch)
        progress = Progress('ways', params.progress_s)
        for way in processor:
            progress.tick()
            tags = dict(way.tags)
            writes = line_dispatch(
                classifier, admin, tags,
                level=boundaries.get(way.id),
                relevant=_is_relevant(tags, keys),
                closed_area=way_is_closed(way) and tags_imply_area(tags))

            if not writes:
                continue
            try:
                geometry = wkb.create_linestring(way)
            except (RuntimeError, osmium.InvalidLocationError):
                continue

            progress.keep()
            for result, search in writes:
                # A named street's search row is the merged street, so it
                # goes to the merge input instead. The end nodes are the
                # whole of what the merge needs: it joins ways that share
                # one and a normalized name.
                ends = None
                if (search and tags.get('name') and result.cls
                        and params.is_merge_class(result.cls)):
                    ends = (way.nodes[0].ref, way.nodes[-1].ref)
                sink.add(way.id, result, tags, geometry, 'line', ends, search=search)
        counts = sink.close()
        progress.done()
        conn.commit()
    return counts


def run_areas(extract: Path, schema: str, model_dir: Path, styles_dir: Path) -> dict[str, int]:
    classifier, params, keys = _setup(model_dir, styles_dir)
    wkb = osmium.geom.WKBFactory()
    processor = (osmium.FileProcessor(extract, E.NODE | E.WAY | E.RELATION | E.AREA)
                 .with_areas()
                 .with_filter(osmium.filter.EntityFilter(E.AREA))
                 .with_filter(osmium.filter.EmptyTagFilter())
                 .with_filter(osmium.filter.KeyFilter(*sorted(keys))))

    with db.connection() as conn:
        sink = RenderSink(conn, schema, params, params.copy_batch)
        progress = Progress('areas', params.progress_s)
        for area in processor:
            progress.tick()
            tags = dict(area.tags)
            bits = classifier.tag_bits(tags)
            result = classifier.classify(bits, 'polygon')
            if not worth_keeping(result, tags):
                continue
            if area.from_way() and drawn_as_line(classifier, bits, tags, result):
                continue
            # Negative for relations, so a relation and a way with the same
            # id do not collide.
            osm_id = area.orig_id() if area.from_way() else -area.orig_id()
            try:
                geometry = wkb.create_multipolygon(area)
            except RuntimeError:
                continue
            progress.keep()
            sink.add(osm_id, result, tags, geometry, 'polygon')
        counts = sink.close()
        progress.done()
        conn.commit()
    return counts


def run(extract: Path, schema: str, model_dir: Path, styles_dir: Path,
        pass_workers: int = 1) -> dict[str, dict]:
    """Pass 0, then the three passes, `pass_workers` of them at a time.

    Not all three by default: the ways and areas passes each hold a location
    store over every node of the file, and on Germany two of them at once
    outgrew 15 GB of RAM and 16 GB of swap. The nodes pass holds none, so 2
    runs it beside the ways pass and the areas pass after them.
    """
    params = params_module.load(model_dir, styles_dir)
    boundaries = boundary_levels(extract, params.progress_s)

    with ProcessPoolExecutor(max_workers=pass_workers) as pool:
        jobs = {
            'nodes': pool.submit(run_nodes, extract, schema, model_dir, styles_dir),
            'ways': pool.submit(run_ways, extract, schema, model_dir, styles_dir, boundaries),
            'areas': pool.submit(run_areas, extract, schema, model_dir, styles_dir),
        }
        return {'boundary_ways': len(boundaries),
                **{name: job.result() for name, job in jobs.items()}}

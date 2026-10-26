"""The SQL steps, in the order of DESIGN.md "Import".

Every function takes (conn, schema) plus what it needs, returns a row count,
and is timed by run.py -- every step is measured (DESIGN.md "Principles"),
and a step that doubles the import has to be visible in the step that caused it.
"""

from __future__ import annotations

import logging

from psycopg import sql

from importer import tables as t

log = logging.getLogger('importer')

#: 3857 units per degree of longitude. Exact, because x is linear in
#: longitude -- which is what lets a degree-sized union cell be expressed in
#: the units the geometry is stored in.
UNITS_PER_DEGREE = 20037508.342789244 / 180.0


def _table(schema: str, name: str) -> sql.Identifier:
    return sql.Identifier(schema, name)


def band_lines(conn, schema: str, params, band) -> int:
    """Fill osm_line<suffix>.

    Lines are selected by the *class's* minzoom, not the row's. A row's
    minzoom is max(class, size), and OSM splits a motorway into one way per
    junction, so no single way passes the size test at low zoom -- selecting
    on the row leaves 36 lines in _z6 for all of Schleswig-Holstein. The
    merge is what puts the road back together, so the size test belongs
    after it: a merged run shorter than a pixel is dropped below.
    """
    classes = [cls for cls, zoom in params.class_minzoom.items() if zoom <= band.zoom_max]
    if not classes:
        return 0

    target = _table(schema, 'osm_line' + band.suffix)
    source = _table(schema, 'osm_line')
    pixel = 2.0 * band.tolerance_m

    if band.union_cell_deg:
        # A merged run's minzoom is its *class's* minzoom. Selection is by
        # class (above), so visibility has to be too, and the band's own
        # size test is the pixel filter at the bottom: a run shorter than a
        # pixel at the band's finest zoom is dropped.
        #
        # min() over the ways the run was built from -- the short ways the
        # merge exists to rescue -- would give every motorway and trunk run
        # in _z6 on `de_sh` minzoom 7, and the render query's `minzoom <= z`
        # would hide all 251 of them, and the national border, at z5 and z6:
        # in the table, and on no tile. Re-applying the per-line
        # size rule to the merged length does not rescue them either -- 8 px
        # at z5 is 39 km, and after ST_LineMerge breaks at every ramp and
        # the grid cuts at every cell edge, almost no run is that long.
        statement = sql.SQL("""
            insert into {target} (osm_id, class, name, label, z_order, minzoom, minzoom_label, geom)
            select 0, class, null, null, z_order, class_zoom, null, geom
            from (
                select c.class, min(c.z_order) z_order, z.zoom class_zoom,
                       (st_dump(st_simplifypreservetopology(
                            st_linemerge(st_collect(c.geom)), %(tolerance)s))).geom geom
                from (
                    select class, geom, z_order,
                           floor(st_x(st_startpoint(geom)) / %(cell)s) cx,
                           floor(st_y(st_startpoint(geom)) / %(cell)s) cy
                    from {source} where class = any(%(classes)s)
                ) c
                join unnest(%(classes)s::text[], %(zooms)s::int[]) as z(class, zoom)
                  on z.class = c.class
                group by c.class, z.zoom, cx, cy
            ) d where st_length(geom) >= %(pixel)s
        """).format(target=target, source=source)
    else:
        statement = sql.SQL("""
            insert into {target} (osm_id, class, name, label, z_order, minzoom, minzoom_label, geom)
            select osm_id, class, name, label, z_order, minzoom, minzoom_label,
                   st_simplifypreservetopology(geom, %(tolerance)s)
            from {source}
            where class = any(%(classes)s) and st_length(geom) >= %(pixel)s
        """).format(target=target, source=source)

    cursor = conn.execute(statement, {
        'tolerance': band.tolerance_m, 'pixel': pixel, 'classes': classes,
        'zooms': [params.class_minzoom[cls] for cls in classes],
        'cell': band.union_cell_deg * UNITS_PER_DEGREE or 1.0,
    })
    return cursor.rowcount


def band_polygons(conn, schema: str, params, band) -> int:
    """Fill osm_polygon<suffix>.

    Polygons keep the row's own minzoom: unlike a road, a small lake really
    is small, and its size is the property the threshold is about.
    """
    target = _table(schema, 'osm_polygon' + band.suffix)
    source = _table(schema, 'osm_polygon')
    pixel_area = (2.0 * band.tolerance_m) ** 2

    if band.union_cell_deg:
        statement = sql.SQL("""
            insert into {target} (osm_id, class, name, label, z_order, minzoom, minzoom_label, geom)
            select 0, class, null, null, z_order, minzoom, null, geom from (
                select class, min(z_order) z_order, min(minzoom) minzoom,
                       (st_dump(st_makevalid(st_simplifypreservetopology(
                            st_union(geom), %(tolerance)s)))).geom geom
                from (
                    select class, geom, minzoom, z_order,
                           floor(st_x(st_pointonsurface(geom)) / %(cell)s) cx,
                           floor(st_y(st_pointonsurface(geom)) / %(cell)s) cy
                    -- The ocean is excluded here and inserted from the
                    -- simplified osmdata set instead: unioning a whole
                    -- state's full-resolution coastline at z6 is both slow
                    -- and pointless, which is why osmdata publishes two
                    -- resolutions.
                    from {source} where minzoom <= %(zoom_max)s and class <> 'cls_ocean'
                ) c group by class, cx, cy
            ) d where st_area(geom) >= %(pixel_area)s and st_geometrytype(geom) = 'ST_Polygon'
        """).format(target=target, source=source)
    else:
        statement = sql.SQL("""
            insert into {target} (osm_id, class, name, label, z_order, minzoom, minzoom_label, geom)
            select osm_id, class, name, label, z_order, minzoom, minzoom_label, geom from (
                select osm_id, class, name, label, z_order, minzoom, minzoom_label,
                       (st_dump(st_makevalid(
                            st_simplifypreservetopology(geom, %(tolerance)s)))).geom geom
                from {source} where minzoom <= %(zoom_max)s and st_area(geom) >= %(pixel_area)s
            ) d where st_geometrytype(geom) = 'ST_Polygon'
        """).format(target=target, source=source)

    cursor = conn.execute(statement, {'tolerance': band.tolerance_m, 'zoom_max': band.zoom_max,
                                      'pixel_area': pixel_area,
                                      'cell': band.union_cell_deg * UNITS_PER_DEGREE or 1.0})
    return cursor.rowcount


def build_bands(conn, schema: str, params) -> dict[str, int]:
    """Every band table, coarsest last so the finest is built from warm cache."""
    counts: dict[str, int] = {}
    for band in params.bands:
        counts['osm_line' + band.suffix] = band_lines(conn, schema, params, band)
        counts['osm_polygon' + band.suffix] = band_polygons(conn, schema, params, band)
        conn.commit()
        log.info('  band %s: %s lines, %s polygons', band.suffix,
                 counts['osm_line' + band.suffix], counts['osm_polygon' + band.suffix])
    return counts


# --- street merge --------------------------------------------------------

class UnionFind:
    """Path-halving union-find over way ids."""

    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, item: int) -> int:
        parent = self.parent
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def components(rows) -> dict[int, int]:
    """{way id: component id} for ways sharing an end node *and* a name.

    A graph walk, which is why it is Python and not SQL: a recursive CTE
    over 150 000 edges is minutes of work that path-halving does in under a
    second, and the input is four small columns.

    The name is part of the key, not a filter applied afterwards: two
    different streets meeting at a junction share a node. A merge by
    proximity, with no name test, would make Bahnhofstraße in one village one
    object with Bahnhofstraße in the next.
    """
    union = UnionFind()
    seen: dict[tuple[int, str], int] = {}
    for osm_id, search_name, n1, n2 in rows:
        union.find(osm_id)
        for node in (n1, n2):
            key = (node, search_name)
            other = seen.get(key)
            if other is None:
                seen[key] = osm_id
            else:
                union.union(osm_id, other)
    return {osm_id: union.find(osm_id) for osm_id in union.parent}


def merge_streets(conn, schema: str, classifier) -> int:
    """One osm_search_object row per connected, same-named run of street."""
    with conn.cursor(name='street_ends') as cursor:
        cursor.execute(sql.SQL('select osm_id, search_name, n1, n2 from {}').format(
            _table(schema, '_street_ends')))
        assignment = components(cursor)
    if not assignment:
        return 0

    conn.execute(sql.SQL(
        'create unlogged table {} (osm_id bigint, component bigint)').format(
        _table(schema, '_street_component')))
    with conn.cursor().copy(sql.SQL('copy {} (osm_id, component) from stdin').format(
            _table(schema, '_street_component'))) as copy:
        for osm_id, component in assignment.items():
            copy.write(f'{osm_id}\t{component}\n')
    conn.execute(sql.SQL('create index on {} (osm_id)').format(
        _table(schema, '_street_component')))

    # The category tree, so the merged row carries the same expanded
    # categories and importance a per-object row would.
    conn.execute(sql.SQL(
        'create unlogged table {} (category text primary key, categories text[], importance smallint)'
    ).format(_table(schema, '_category_expanded')))
    with conn.cursor().copy(sql.SQL(
            'copy {} (category, categories, importance) from stdin').format(
            _table(schema, '_category_expanded'))) as copy:
        for category in classifier.categories.ancestors:
            expanded = '{' + ','.join(f'"{c}"' for c in classifier.categories.expand([category])) + '}'
            copy.write(f'{category}\t{expanded}\t{classifier.categories.importance[category]}\n')

    cursor = conn.execute(sql.SQL("""
        with merged as (
            select c.component, e.search_name,
                   array_agg(distinct e.osm_id) ids,
                   min(e.name) name, min(e.phon_name) phon_name,
                   min(e.category) category, min(e.class) class,
                   st_multi(st_linemerge(st_collect(st_transform(l.geom, 4326)))) geom
            from {component} c
            join {ends} e using (osm_id)
            join {lines} l on l.osm_id = e.osm_id
            group by c.component, e.search_name
        )
        insert into {target}
            (osm_ids, name, search_name, search_text, phon_name, search_city,
             categories, category, importance, class,
             addr_street, addr_housenumber, addr_postcode, addr_city,
             geom_point, geom_line, geom_polygon, geom_center, tags)
        select m.ids, m.name, m.search_name, m.search_name, m.phon_name, null,
               coalesce(x.categories, '{{}}'), m.category, x.importance, m.class,
               null, null, null, null,
               null, m.geom, null,
               st_lineinterpolatepoint(st_geometryn(m.geom, 1), 0.5), null
        from merged m left join {expanded} x on x.category = m.category
        where x.importance is distinct from 0
    """).format(component=_table(schema, '_street_component'),
                ends=_table(schema, '_street_ends'),
                lines=_table(schema, 'osm_line'),
                expanded=_table(schema, '_category_expanded'),
                target=_table(schema, 'osm_search_object')))
    conn.commit()
    return cursor.rowcount


def resolve_id_object(conn, schema: str) -> int:
    """Link each address to the named object it sits on, if it has one."""
    count = conn.execute(sql.SQL("""
        update {a} a set id_object = s.id from {o} s
        where a.id_object is null and s.osm_ids = array[a.osm_id]
    """).format(a=_table(schema, 'osm_search_address'),
                o=_table(schema, 'osm_search_object'))).rowcount
    conn.commit()
    return count


def build_dictionaries(conn, schema: str, classifier, languages,
                       street_classes) -> dict[str, int]:
    """osm_street and osm_category_term.

    Street matching runs against the small distinct-name table rather than
    the main one; the term dictionary is what lets the phrase
    parser turn "Bäckerei" into a category.

    `street_classes` is not optional decoration. The dictionary is derived
    from the search objects with a street class, and selecting on `geom_line is not null` instead sweeps in
    every named line that got a search row -- rivers, railways, and the
    named lines with no render class at all. The address search matches the
    user's street against this table, so a stream called Mühlbach would
    come back as a street.
    """
    counts = {}
    counts['osm_street'] = conn.execute(sql.SQL("""
        insert into {street} (search_street, phon_street, n)
        select search_name, min(phon_name), count(*)
        from {objects}
        where geom_line is not null and search_name <> '' and class = any(%(classes)s)
        group by search_name
    """).format(street=_table(schema, 'osm_street'),
                objects=_table(schema, 'osm_search_object')),
        {'classes': list(street_classes)}).rowcount

    from lib import text as text_module
    rows = set()
    named: dict[tuple[str, str], set[str]] = {}
    for node_id in classifier.categories.ancestors:
        for language in languages:
            for position, value in enumerate(_terms(classifier, node_id, language)):
                term = text_module.normalize(value)
                if term:
                    rows.add((term, node_id, text_module.phonetic(term), language))
                    if position == 0:
                        named.setdefault((term, language), set()).add(node_id)
    # A term that is some category's name means that category. The deep tree
    # repeats a parent's word among its children's synonyms -- "restaurant"
    # is a term of a dozen cuisines -- and the phrase parser takes one
    # category per term, so without this "restaurant" could come back as
    # the Georgian one.
    rows = {row for row in rows
            if (row[0], row[3]) not in named or row[1] in named[(row[0], row[3])]}

    with conn.cursor().copy(sql.SQL(
            'copy {} (term, category, phon_term, lang) from stdin').format(
            _table(schema, 'osm_category_term'))) as copy:
        for term, category, phonetic, language in sorted(rows):
            copy.write(f'{term}\t{category}\t{phonetic}\t{language}\n')
    counts['osm_category_term'] = len(rows)
    conn.commit()
    return counts


def _terms(classifier, node_id: str, language: str) -> list[str]:
    node = classifier.categories.nodes.get(node_id, {})
    values = [node.get(f'name_{language}')]
    values.extend(node.get(f'terms_{language}') or [])
    return [v for v in values if v]


def drop_working_tables(conn, schema: str) -> None:
    for name in ('_street_ends', '_street_component', '_category_expanded'):
        conn.execute(sql.SQL('drop table if exists {}').format(_table(schema, name)))
    conn.commit()


# --- indexes -------------------------------------------------------------

#: A predicate that selects more than this share of a table earns nothing
#: over a plain index and costs a planner decision.
PREDICATE_MAX_SHARE = 0.5

RENDER_TABLES_FOR_INDEXES = ('osm_point', 'osm_line', 'osm_polygon', 'osm_building', 'osm_label',
                             'osm_contour')


def table_classes(conn, schema: str) -> dict[str, dict[str, int]]:
    """{table: {class: row count}} for the full render tables.

    Shared with the style generator, which asks the same question to decide
    which table a layer reads -- see `lib.db.table_classes`.
    """
    from lib import db

    return db.table_classes(conn, schema, RENDER_TABLES_FOR_INDEXES)


def layer_index_statements(conn, schema: str, params) -> list[sql.Composed]:
    """One partial GiST per layer, on whichever table holds its classes.

    The table is decided from the data, not from the layer's mode:
    `roads_fill` has mode `fill` over line classes,
    and `buildings` has mode `fill` but belongs to osm_building, which
    osm_polygon explicitly excludes.
    """
    present = table_classes(conn, schema)
    known = {cls for classes in present.values() for cls in classes}
    statements: list[sql.Composed] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for layer, classes in params.layer_class_sets(known):
        for table, counts in present.items():
            matching = sorted(classes & set(counts))
            if not matching:
                continue
            total = sum(counts.values())
            selected = sum(counts[c] for c in matching)
            # Near-total coverage: one plain index serves the table better
            # than a predicate the planner has to reason about.
            key = (table, () if selected > total * PREDICATE_MAX_SHARE else tuple(matching))
            if key in seen:
                continue
            seen.add(key)
            target = _table(schema, table)
            # Named explicitly: every partial index here is on the same
            # table and column, so Postgres would derive one name for all
            # of them -- and four connections build them at once, so even
            # distinct auto-names would race.
            if not key[1]:
                statements.append(sql.SQL('create index {} on {} using gist (geom)').format(
                    sql.Identifier(f'{table}_geom_idx'), target))
            else:
                statements.append(sql.SQL(
                    'create index {} on {} using gist (geom) where class = any({})'
                ).format(sql.Identifier(f'{table}_{layer}_idx'[:t.NAME_MAX]),
                         target, sql.Literal(matching)))
    return statements


def all_index_statements(conn, schema: str, params, tables) -> list[sql.Composed]:
    statements = []
    for table in tables:
        statements.extend(t.index_statements(schema, table))
    statements.extend(layer_index_statements(conn, schema, params))
    # osm_line carries the line labels, which read it on minzoom_label.
    statements.append(sql.SQL(
        'create index {} on {} using gist (geom) where minzoom_label is not null'
    ).format(sql.Identifier('osm_line_labels_idx'), _table(schema, 'osm_line')))
    return statements


def create_indexes(schema: str, statements, workers: int, progress_s: float) -> int:
    """Build them over several connections at once.

    Index builds are mostly independent CPU and I/O, so they run on
    `workers` connections in parallel.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from lib import db

    def build(statement):
        with db.connection(autocommit=True) as conn:
            conn.execute(statement)

    started = last = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = [pool.submit(build, statement) for statement in statements]
        for done, job in enumerate(as_completed(jobs), 1):
            job.result()
            now = time.monotonic()
            if now - last >= progress_s or done == len(jobs):
                last = now
                log.info('  indexes: %d/%d, %.0f s', done, len(jobs), now - started)
    return len(statements)


def order_tables(conn, schema: str, tables) -> None:
    """Rewrite each table in the order of its `order_by`, before its indexes.

    CLUSTER on a btree over the expression, which Postgres runs as a
    sequential scan and a sort rather than an index walk -- the walk would
    be one random read per row, the cost this step removes from the tiles.
    Before the index build, because CLUSTER rebuilds every index the table
    has; the btree is dropped again, nothing queries it.
    """
    for table in tables:
        if table.order_by is None:
            continue
        index = f'{table.name}_order_idx'
        conn.execute(sql.SQL('create index {} on {} ({})').format(
            sql.Identifier(index), _table(schema, table.name), sql.SQL(table.order_by)))
        conn.execute(sql.SQL('cluster {} using {}').format(
            _table(schema, table.name), sql.Identifier(index)))
        conn.execute(sql.SQL('drop index {}').format(sql.Identifier(schema, index)))
        conn.commit()


def cluster_bands(conn, schema: str, params) -> None:
    """GiST then CLUSTER, so a low-zoom tile reads a few contiguous pages.

    Before SET LOGGED, but not because SET LOGGED would undo it. Measured: the
    rewrite copies the table in physical order, and a table clustered to
    correlation 1.0000 is still at 1.0000 afterwards. The order is right
    because clustering an UNLOGGED table writes no WAL for the rewrite,
    which is the whole reason the import runs unlogged.
    """
    for band in params.bands:
        for base in t.BANDED:
            table = t.band_table(base, band.suffix)
            name = sql.Identifier(f'{table.name}_geom_idx')
            conn.execute(sql.SQL('create index {} on {} using gist (geom)').format(
                name, _table(schema, table.name)))
            conn.execute(sql.SQL('cluster {} using {}').format(_table(schema, table.name), name))
        conn.commit()


def finish(conn, schema: str, tables: list) -> None:
    for table in tables:
        if table.unlogged:
            conn.execute(sql.SQL('alter table {} set logged').format(_table(schema, table.name)))
    conn.commit()
    for table in tables:
        conn.execute(sql.SQL('vacuum analyze {}').format(_table(schema, table.name)))

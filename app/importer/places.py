"""The address path: the places each search row lies in.

`id_places` on `osm_search_object` and `osm_search_address` holds ids of
`osm_search_object` rows, from the state down: every administrative area of
`places.levels` the row intersects. A point lies in one area per level; a
street along or across a border lies in each area it touches, so the
relation is many-to-many. An area object lies in an area that holds at
least `places.area_share` of it: a park split across a municipal border is
found under both municipalities, but a district is not in the Ortsteile it
contains, nor in a neighbour whose boundary misses its own by a sliver.

Only areas: a place mapped as a node has no border, so nothing can be said
to lie in it. The path stops at the finest area, and the phrase mode finds
"Dorfstraße Höhndorf" near such a place instead (search/phrase.py).

An administrative area lies only in areas of a lower admin level, whatever
the overlap: a district (6) and a municipality (8) can share one outline,
each holding all of the other, and the district must not lie in the
municipality. Same-level neighbours and finer units never qualify.

Only objects of `places.categories` get a path -- a river would otherwise
collect every municipality it passes -- and every address does.
"""

from __future__ import annotations

from psycopg import sql

AREA = '_place_area'
OWN = '_place_own'
LINK = '_place_link'

#: The search-only categories model/classifier.yaml gives an administrative
#: area per admin_level.
ADMIN_CATEGORY = 'cat_geography_admin_{level}'


#: What a place node is, and what it is merged into (`merge_nodes`).
PLACE_CATEGORY = 'cat_geography_places'
ADMIN_AREA = 'cat_geography_admin'
#: A place kind no category names (`place=country`, `place=state`): the
#: area's own category says more, "Staat" rather than "Sonstiger Ort".
PLACE_OTHER = 'cat_geography_places_other'


def _table(schema: str, name: str) -> sql.Identifier:
    return sql.Identifier(schema, name)


def merge_nodes(conn, schema: str) -> int:
    """Fold a place node into the administrative area of its name around it.

    Unmerged, "Berlin" is two results, the `place=city` node first
    (importance 100) and the Land's polygon (20) below it, and a client
    highlights a point. Merged, it is one row: the area's, with its polygon and id, so the address
    paths that name it are unchanged. It takes from the node what a search
    for the name means -- `category` (Stadt, not Bundesland) and class, the higher
    importance, and the centre, the label point rather than any interior
    point of the outline. The admin category stays in `categories`, which
    is where a path entry takes its name from (search/shape.py). Both OSM
    ids stay, and the tags are both sets, the relation's winning where they
    share a key: a capital's node says `admin_level=2`, the level of the
    country it is the capital of, and the area is still a municipality.

    A node inside several areas of its name joins the smallest; an area
    that holds several nodes of its name takes the most important. Nodes
    and areas of different names are left alone: a village node in a
    municipality called something else is a place of its own.
    """
    count = conn.execute(sql.SQL("""
        with inside as (
            select distinct on (n.id) n.id as node, a.id as area, n.importance
            from {objects} n
            join {objects} a
              on a.search_name = n.search_name
             and a.geom_polygon && n.geom_point
             and st_covers(a.geom_polygon, n.geom_point)
            where n.geom_point is not null and n.search_name <> ''
              and n.categories && array[{place}]
              and a.categories && array[{admin}]
            order by n.id, st_area(a.geom_polygon), a.id
        ), pair as (
            select distinct on (area) node, area
            from inside
            order by area, importance desc, node
        ), merged as (
            update {objects} a
            set category = case when n.category = {other} then a.category else n.category end,
                class = case when n.category = {other} then a.class else n.class end,
                categories = array(select c from unnest(a.categories || n.categories)
                                   with ordinality u(c, i) group by c order by min(i)),
                importance = greatest(a.importance, n.importance),
                geom_center = n.geom_center,
                osm_ids = a.osm_ids || n.osm_ids,
                tags = coalesce(n.tags, '{{}}') || coalesce(a.tags, '{{}}')
            from pair p join {objects} n on n.id = p.node
            where a.id = p.area
            returning p.node
        )
        delete from {objects} o using merged m where o.id = m.node
    """).format(objects=_table(schema, 'osm_search_object'),
                  place=sql.Literal(PLACE_CATEGORY), admin=sql.Literal(ADMIN_AREA),
                  other=sql.Literal(PLACE_OTHER))).rowcount
    conn.commit()
    return count


def resolve(conn, schema: str, params) -> dict[str, int]:
    levels = list(params.place_levels)
    # Literals rather than bind parameters: several of these statements are
    # CREATE TABLE AS, which is a utility statement and takes none.
    names = {
        'objects': _table(schema, 'osm_search_object'),
        'addresses': _table(schema, 'osm_search_address'),
        'area': _table(schema, AREA),
        'own': _table(schema, OWN),
        'admin_pattern': sql.Literal('^' + ADMIN_CATEGORY.format(level=r'(\d+)') + '$'),
        'link': _table(schema, LINK),
        'levels': sql.Literal(levels),
        'area_categories': sql.Literal([ADMIN_CATEGORY.format(level=level) for level in levels]),
        'categories': sql.Literal(list(params.place_categories)),
        'vertices': sql.Literal(params.place_subdivide_vertices),
        'area_share': sql.Literal(params.place_area_share),
    }

    def run(statement: str) -> int:
        return conn.execute(sql.SQL(statement).format(**names)).rowcount

    counts = {}
    # Freshly COPYed, so the planner has no statistics for the joins below.
    run('analyze {objects}')
    run('analyze {addresses}')

    # Subdivided, so that the exact test after the && runs on a piece of a
    # few hundred vertices and not on a whole district outline.
    run("""
        create unlogged table {area} as
        select o.id, l.level, st_subdivide(o.geom_polygon, {vertices}) as g
        from {objects} o
        join unnest({area_categories}::text[], {levels}::int[]) as l(category, level)
          on l.category = any(o.categories)
        where o.geom_polygon is not null
    """)
    run('create index on {area} using gist (g)')
    run('analyze {area}')

    # The admin level of every row that is an administrative area itself,
    # of any level, not only of `levels`: an Amt (7) lies in its district.
    run("""
        create unlogged table {own} as
        select o.id, min(substring(c from {admin_pattern})::int) as level
        from {objects} o, unnest(o.categories) c
        where c ~ {admin_pattern}
        group by o.id
    """)
    run('create unique index on {own} (id)')
    run('analyze {own}')

    run('create unlogged table {link} (kind "char", id integer, place integer, level integer)')
    counts['objects'] = run("""
        insert into {link}
        select distinct 'o', o.id, s.id, s.level
        from {objects} o
        join {area} s
          on s.g && coalesce(o.geom_point, o.geom_line)
         and st_intersects(s.g, coalesce(o.geom_point, o.geom_line))
        left join {own} w on w.id = o.id
        where o.geom_polygon is null and o.categories && {categories} and s.id <> o.id
          and (w.level is null or s.level < w.level)
    """)
    # The share summed over the pieces of each area. An object inside one
    # piece is settled by st_covers without computing an intersection.
    counts['objects'] += run("""
        insert into {link}
        select 'o', o.id, s.id, s.level
        from {objects} o
        join {area} s on s.g && o.geom_polygon
        left join {own} w on w.id = o.id
        where o.geom_polygon is not null and o.categories && {categories} and s.id <> o.id
          and (w.level is null or s.level < w.level)
        group by o.id, s.id, s.level
        having sum(case when st_covers(s.g, o.geom_polygon) then st_area(o.geom_polygon)
                        else st_area(st_intersection(s.g, o.geom_polygon)) end)
               >= {area_share} * max(st_area(o.geom_polygon))
    """)
    counts['addresses'] = run("""
        insert into {link}
        select distinct 'a', a.id, s.id, s.level
        from {addresses} a
        join {area} s on s.g && a.geom and st_intersects(s.g, a.geom)
    """)
    run('create index on {link} (kind, id)')
    run('analyze {link}')

    counts['object_paths'] = run("""
        update {objects} o set id_places = l.ids
        from (select id, array_agg(place order by level, place) as ids
              from {link} where kind = 'o' group by id) l
        where o.id = l.id
    """)
    counts['address_paths'] = run("""
        update {addresses} a set id_places = l.ids
        from (select id, array_agg(place order by level, place) as ids
              from {link} where kind = 'a' group by id) l
        where a.id = l.id
    """)

    for name in (AREA, OWN, LINK):
        conn.execute(sql.SQL('drop table {}').format(_table(schema, name)))
    conn.commit()
    return counts

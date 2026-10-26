"""Count how many objects of an extract each classifier rule matches.

Runs inside the app container (needs pyosmium):

    docker compose -f docker-compose.local.yml exec app python tools/rule_stats.py \\
        model/classifier.yaml model/generated/classifier.yaml \\
        /data/downloads/schleswig-holstein-latest.osm.pbf > app/tools/.cache/rule_stats_sh.json

Output: JSON `{category id: object count}` for every rule, counting an
object for every rule it matches (not only the first), the same semantics
the importer uses for categories. Rules are indexed by their first
condition so each object only evaluates the rules that mention one of its
tags.
"""

from __future__ import annotations

import collections
import json
import sys

import osmium
import yaml


def parse_match(expr: str) -> list[list[tuple[str, str]]]:
    """Tag terms only: a term without `=` restricts the geometry, which this ignores."""
    return [[tuple(t.strip().split('=', 1)) for t in alt.split('+') if '=' in t]
            for alt in expr.split('|')]


def main() -> None:
    rules = [rule for path in sys.argv[1:-1] for rule in yaml.safe_load(open(path)) or []]
    by_first: dict[tuple[str, str], list[tuple[list[tuple[str, str]], str]]] = collections.defaultdict(list)
    for rule in rules:
        target = rule['category']
        for conj in parse_match(rule['match']):
            by_first[conj[0]].append((conj[1:], target))

    counts: collections.Counter[str] = collections.Counter()
    total = 0
    for etype in (osmium.osm.NODE, osmium.osm.WAY, osmium.osm.RELATION):
        fp = osmium.FileProcessor(sys.argv[-1], etype).with_filter(osmium.filter.EmptyTagFilter())
        for obj in fp:
            total += 1
            tags = dict(obj.tags)
            hit = set()
            for k, v in tags.items():
                for first in ((k, v), (k, '*')):
                    for rest, target in by_first.get(first, ()):
                        if all(tags.get(rk) is not None and (rv == '*' or tags[rk] == rv) for rk, rv in rest):
                            hit.add(target)
            counts.update(hit)
        print(f'{etype}: {total:,} objects so far', file=sys.stderr)
    json.dump(dict(counts.most_common()), sys.stdout, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()

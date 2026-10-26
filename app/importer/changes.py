"""What moved against the previous import of the area.

A report for the import log, not a check that fails: a model change moves
counts on purpose, and OSM grows by a few percent between imports months
apart. What it is for is the change nobody meant -- a broken rule, a lost
input -- which nothing else notices, since a schema with a class missing
serves and renders like any other.

Both sides come from `import_meta`, so the previous schema is not queried
beyond its one row. Two sets of counts are compared: the steps' row counts
(`row_counts`, per pass and table), and the rows per class of each render
table (`table_classes`). The second is the one that matters: a broken rule
moves one class by 100 % while its table stays within 1 %.
"""

from __future__ import annotations

from typing import NamedTuple


class Change(NamedTuple):
    key: str          # `ways.line`, or `osm_line cls_road_primary`
    old: int
    new: int

    @property
    def percent(self) -> float | None:
        """The change relative to the old count; None for a count that is new."""
        return (self.new - self.old) / self.old * 100 if self.old else None


def counts(meta: dict) -> dict[str, int]:
    """One flat {key: count} from an `import_meta` row."""
    out: dict[str, int] = {}

    def walk(prefix: str, value) -> None:
        if isinstance(value, dict):
            for name, inner in value.items():
                walk(f'{prefix}.{name}' if prefix else name, inner)
        elif isinstance(value, int) and not isinstance(value, bool):
            out[prefix] = value

    walk('', meta.get('row_counts') or {})
    for table, classes in (meta.get('table_classes') or {}).items():
        for cls, rows in classes.items():
            out[f'{table} {cls}'] = rows
    return out


def compare(old: dict[str, int], new: dict[str, int], *,
            change_pct: float, min_rows: int) -> list[Change]:
    """The counts that moved, the largest relative change first.

    One that appeared or vanished is always listed, however small: that is
    what a broken rule looks like on a class with few rows. A key only the
    old side has counts as 0 on the new one and the other way round, so a
    count recorded by one import version and not the other shows as well.
    """
    moved = []
    for key in old.keys() | new.keys():
        change = Change(key, old.get(key, 0), new.get(key, 0))
        if change.old == change.new:
            continue
        if (not change.old or not change.new
                or (abs(change.new - change.old) >= min_rows
                    and abs(change.percent) > change_pct)):
            moved.append(change)
    return sorted(moved, key=lambda c: (c.percent is not None, -abs(c.percent or 0), c.key))


def report(previous: str, changes: list[Change], compared: int, change_pct: float) -> list[str]:
    """The log lines: a headline, then one line per change."""
    if not changes:
        return [f'against {previous}: none of {compared} counts moved by more than {change_pct:g} %']
    lines = [f'against {previous}: {len(changes)} of {compared} counts moved by more than '
             f'{change_pct:g} %, or appeared or vanished']
    for change in changes:
        moved = 'new' if change.percent is None else f'{change.percent:+.1f} %'
        lines.append(f'  {change.key}: {change.old:,} -> {change.new:,} ({moved})')
    return lines

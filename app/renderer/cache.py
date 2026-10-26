"""Tile cache: two filesystem tiers, keyed `theme/set/format/z/x/y`.

Every TileMatrixSet caches separately. Every served grid is pre-cached
to its own depth (`precache: {GoogleMapsCompatible: 12,
DE_EPSG_25832_ADV: 8}`), so the cutoff is per set, not a constant: a UTM level 9 tile is on-demand
while a Web Mercator z9 tile is pre-cached.

From a set's `nocache_from` level on, nothing is cached at all. A tile that
deep renders no slower than a z16 one, but two requests rarely ask for the
same one, so caching it would only push out tiles that are asked for again.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

log = logging.getLogger('renderer')

#: Every component becomes a path segment under the cache root, and all of
#: them arrive from a request -- XYZ takes theme and format from the path,
#: WMTS takes LAYER/TILEMATRIXSET/FORMAT from the query string, where a
#: `/` or a `..` is perfectly legal to send. Restricting them to a
#: name shape is what stops a request addressing a path of its choosing.
_SAFE = re.compile(r'\A[A-Za-z0-9][A-Za-z0-9._-]*\Z')


#: What a set with no `precache` entry is assumed to be seeded to. It is
#: the Web Mercator depth, and a value here is better than a set whose two tiers disagree about who owns
#: a level.
DEFAULT_DEPTH = 12


class InvalidTileKey(ValueError):
    """A key that cannot address anything.

    Raised when the key is built, so every tier inherits the check.
    Callers on the request path treat it as a miss: nothing valid can ever
    have been stored under a key that cannot be built.
    """


def check_component(name: str, value: str) -> str:
    if not isinstance(value, str) or not _SAFE.match(value):
        raise InvalidTileKey(f'invalid {name} for a cache key: {value!r}')
    return value


@dataclass(frozen=True, slots=True)
class TileKey:
    theme: str
    tile_matrix_set: str
    format: str
    z: int
    x: int
    y: int

    def __post_init__(self) -> None:
        check_component('theme', self.theme)
        check_component('tile_matrix_set', self.tile_matrix_set)
        check_component('format', self.format)
        for name in ('z', 'x', 'y'):
            value = getattr(self, name)
            # bool is an int subclass and would render as True/False.
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidTileKey(f'invalid {name} for a cache key: {value!r}')

    def __str__(self) -> str:
        return (f'{self.theme}/{self.tile_matrix_set}/{self.format}/'
                f'{self.z}/{self.x}/{self.y}')


def cache_key(theme: str, tile_matrix_set: str, fmt: str, z: int, x: int, y: int) -> str:
    return str(TileKey(theme, tile_matrix_set, fmt, z, x, y))


class TileCache(Protocol):
    def get(self, key: str) -> bytes | None: ...
    def set(self, key: str, data: bytes) -> None: ...
    def clear_theme(self, theme: str) -> None: ...
    def clear_all(self) -> None: ...


class FilesystemCache:
    """One tier, one directory tree. The key is the path."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        parts = key.split('/')
        if len(parts) != 6:
            raise InvalidTileKey(f'not a tile key: {key!r}')
        theme, tms, fmt, z, x, y = parts
        for name, value in (('theme', theme), ('tile_matrix_set', tms), ('format', fmt)):
            check_component(name, value)
        for value in (z, x, y):
            if not value.lstrip('-').isdigit():
                raise InvalidTileKey(f'not a tile key: {key!r}')
        return self.root / theme / tms / fmt / z / x / f'{y}.{fmt}'

    def get(self, key: str) -> bytes | None:
        try:
            return self._path(key).read_bytes()
        except (FileNotFoundError, NotADirectoryError):
            return None

    def set(self, key: str, data: bytes) -> None:
        """Write atomically.

        Two requests for the same uncached tile race by construction --
        a browser asks for a viewport at once -- and a half-written file
        read by the other is a corrupt tile that stays cached.
        """
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(handle, 'wb') as out:
                out.write(data)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def clear_theme(self, theme: str) -> None:
        import shutil

        check_component('theme', theme)
        shutil.rmtree(self.root / theme, ignore_errors=True)

    def clear_all(self) -> None:
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def evict_lru(self, max_bytes: int) -> int:
        """Drop the least recently used tiles until the tier fits.

        Only the on-demand tier is evicted: the pre-cache tier is
        generated deliberately and evicting it would mean rendering it
        again.
        """
        files = [(p.stat().st_atime, p.stat().st_size, p)
                 for p in self.root.rglob('*') if p.is_file()]
        total = sum(size for _, size, _ in files)
        removed = 0
        for _, size, path in sorted(files):
            if total <= max_bytes:
                break
            path.unlink(missing_ok=True)
            total -= size
            removed += 1
        return removed


class NullCache:
    """A tier that holds nothing: the `nocache` option."""

    def get(self, key: str) -> bytes | None:
        return None

    def set(self, key: str, data: bytes) -> None:
        pass

    def clear_theme(self, theme: str) -> None:
        pass

    def clear_all(self) -> None:
        pass

    def evict_lru(self, max_bytes: int) -> int:
        return 0


class TileCacheFacade:
    """Routes a tile to the tier that owns its zoom.

    The cutoff is per TileMatrixSet. A single z12 constant only describes
    Web Mercator; with EPSG:25832 pre-cached to level 8, a constant would
    send its level 9-12 tiles to the wrong tier -- looked
    for where they were never written, and written where the pre-cache
    would later overwrite them.
    """

    def __init__(self, precache: TileCache, ondemand: TileCache,
                 depths: dict[str, int], default_depth: int = DEFAULT_DEPTH,
                 nocache_from: dict[str, int] | None = None) -> None:
        self.precache = precache
        self.ondemand = ondemand
        self.uncached = NullCache()
        self.depths = depths
        self.default_depth = default_depth
        self.nocache_from = nocache_from or {}

    def depth_for(self, tile_matrix_set: str) -> int:
        """The deepest level of this set that the pre-cache owns.

        Keyed by the identifier a request sends, not by the CRS code the
        option is written with -- see the module docstring.
        """
        return self.depths.get(tile_matrix_set, self.default_depth)

    def tier_for(self, tile_matrix_set: str, z: int) -> TileCache:
        if z <= self.depth_for(tile_matrix_set):
            return self.precache
        if z >= self.nocache_from.get(tile_matrix_set, z + 1):
            return self.uncached
        return self.ondemand

    def get(self, theme: str, tile_matrix_set: str, fmt: str, z: int, x: int, y: int):
        try:
            key = cache_key(theme, tile_matrix_set, fmt, z, x, y)
        except InvalidTileKey:
            # A miss, not an error: nothing can ever have been stored
            # under a key that cannot be built, and the routes look the
            # cache up before they validate anything.
            return None
        return self.tier_for(tile_matrix_set, z).get(key)

    def set(self, theme: str, tile_matrix_set: str, fmt: str, z: int, x: int, y: int,
            data: bytes) -> None:
        try:
            key = cache_key(theme, tile_matrix_set, fmt, z, x, y)
        except InvalidTileKey:
            log.warning('refusing to cache an unaddressable tile: %s/%s/%s/%s/%s/%s',
                        theme, tile_matrix_set, fmt, z, x, y)
            return
        self.tier_for(tile_matrix_set, z).set(key, data)

    def clear_theme(self, theme: str) -> None:
        self.precache.clear_theme(theme)
        self.ondemand.clear_theme(theme)


def precache_depths(precache_option: dict | None = None,
                    sets: dict | None = None) -> dict[str, int]:
    """`precache:`, limited to the served grids.

    A grid in `precache:` that is not in `serve_grids` is ignored rather
    than refused: it is a depth for a set this deployment does not serve.
    """
    return _per_grid('precache', precache_option, sets)


def nocache_levels(nocache_option: dict | None = None,
                   sets: dict | None = None) -> dict[str, int]:
    """`nocache_from:`, limited to the served grids, as `precache_depths`."""
    return _per_grid('nocache_from', nocache_option, sets)


def _per_grid(name: str, option: dict | None, sets: dict | None) -> dict[str, int]:
    from lib import config
    from renderer import matrix

    option = option if option is not None else (config.opt(name) or {})
    sets = sets if sets is not None else matrix.load()
    return {identifier: int(level)
            for identifier, level in option.items() if identifier in sets}


def cache_root(area: str | None = None) -> Path:
    """Per area, not per schema: a re-import keeps the area's cache."""
    from lib import config

    area = area or config.opt('serve_area')
    return Path(config.opt('data_dir', '/data')) / 'cache' / area


def clear_area(area: str) -> int:
    """Empty both tiers for one area. Returns how many tiles were removed.

    Nothing else empties them. A re-import or a style change leaves every
    cached tile as it was drawn, and a cached tile is served as it is --
    `manage.py drop-cache` calls this, or `pre-cache --force` overwrites.
    """
    root = cache_root(area)
    removed = 0
    for tier in ('precache', 'ondemand'):
        directory = root / tier
        if directory.is_dir():
            removed += sum(1 for path in directory.rglob('*') if path.is_file())
            FilesystemCache(directory).clear_all()
    return removed


def build(area: str | None = None) -> TileCacheFacade:
    """The two tiers for an area, from the options."""
    from lib import config

    if config.opt('nocache'):
        return TileCacheFacade(NullCache(), NullCache(), precache_depths())
    root = cache_root(area)
    return TileCacheFacade(FilesystemCache(root / 'precache'),
                           FilesystemCache(root / 'ondemand'),
                           precache_depths(), nocache_from=nocache_levels())

#!/usr/bin/env python3
"""Read an OM file header and query a value by lat/lon.

This script expects an OM reader library that exposes a minimal interface:
- OmFileReader(path)
- reader.get_dimensions() -> list/tuple
- reader.read() -> flat list/array

If your library uses different method names, update the helpers below.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable, Sequence


try:
    from omfile import OmFileReader  # type: ignore
except ImportError as exc:  # pragma: no cover - runtime dependency
    raise SystemExit(
        "Missing dependency: install an OM reader (e.g. `pip install omfile`) "
        "or replace the import with your local OM reader implementation."
    ) from exc


def get_dimensions(reader: object) -> Sequence[int]:
    if hasattr(reader, "get_dimensions"):
        dims = reader.get_dimensions()
    else:
        dims = getattr(reader, "dimensions", None)
    if dims is None:
        raise ValueError("OM reader does not expose dimensions")
    return list(dims)


def read_all(reader: object) -> Iterable[float]:
    if hasattr(reader, "read"):
        return reader.read()
    raise ValueError("OM reader does not expose read()")


def _wrap_longitude(lon: float) -> float:
    """Normalize longitude to [-180, 180)."""
    return ((lon + 180.0) % 360.0) - 180.0


def _round_away_from_zero(x: float) -> int:
    """Match Swift's round() behavior (ties away from zero)."""
    if x >= 0:
        return int(math.floor(x + 0.5))
    return int(math.ceil(x - 0.5))


class GaussianGridType(str, Enum):
    O320 = "o320"
    O1280 = "o1280"

    @property
    def latitude_lines(self) -> int:
        if self is GaussianGridType.O320:
            return 320
        if self is GaussianGridType.O1280:
            return 1280
        raise ValueError(f"Unsupported Gaussian grid type: {self.value}")

    @property
    def count(self) -> int:
        """Total number of points (ECMWF 'O' reduced Gaussian grids)."""
        l: int = self.latitude_lines
        return 4 * l * (l + 9)

    def nx_of(self, y: int) -> int:
        """Number of longitudes for latitude line y (0..2L-1)."""
        l: int = self.latitude_lines
        if y < l:
            return 20 + y * 4
        return (2 * l - y - 1) * 4 + 20

    def integral(self, y: int) -> int:
        """Prefix sum of nx_of over lines < y."""
        l: int = self.latitude_lines
        if y < l:
            return 2 * y * y + 18 * y
        # Mirror symmetry (matches Swift implementation)
        remaining: int = 2 * l - y
        return self.count - (2 * remaining * remaining + 18 * remaining)


@dataclass(frozen=True)
class ReducedGaussianGrid:
    """Reduced Gaussian grid indexing (subset used by this repo).

    This implements the same nearest-point logic as `GaussianGrid.findPointXY`
    for ECMWF 'O' reduced Gaussian grids (O320/O1280).
    """

    grid_type: GaussianGridType

    def _dy(self) -> float:
        l: int = self.grid_type.latitude_lines
        return 180.0 / (2.0 * float(l) + 0.5)

    def find_point(self, lat: float, lon: float) -> int:
        x, y = self.find_point_xy(lat=lat, lon=lon)
        return self.grid_type.integral(y) + x

    def find_point_xy(self, lat: float, lon: float) -> tuple[int, int]:
        """Nearest neighbor point selection (no fractional position)."""
        l: int = self.grid_type.latitude_lines
        dy: float = self._dy()

        # Swift clamps y to [0, 2*L-2], then checks line y and y+1.
        y_raw: float = float(l) - 1.0 - ((lat - dy / 2.0) / dy)
        y: int = max(0, min(2 * l - 2, int(y_raw)))
        y_upper: int = y + 1

        nx: int = self.grid_type.nx_of(y)
        nx_upper: int = self.grid_type.nx_of(y_upper)
        dx: float = 360.0 / float(nx)
        dx_upper: float = 360.0 / float(nx_upper)

        lon_wrapped: float = _wrap_longitude(lon)
        x0: int = _round_away_from_zero(lon_wrapped / dx)
        x1: int = _round_away_from_zero(lon_wrapped / dx_upper)

        point_lat: float = float(l - y - 1) * dy + dy / 2.0
        point_lon: float = float(x0) * dx
        point_lat_upper: float = float(l - y_upper - 1) * dy + dy / 2.0
        point_lon_upper: float = float(x1) * dx_upper

        dist0: float = (point_lat - lat) ** 2 + (point_lon - lon_wrapped) ** 2
        dist1: float = (point_lat_upper - lat) ** 2 + (point_lon_upper - lon_wrapped) ** 2

        if dist0 < dist1:
            return ((x0 + nx) % nx, y)
        return ((x1 + nx_upper) % nx_upper, y_upper)


def find_point_regular(
    lat: float,
    lon: float,
    lat_min: float,
    lon_min: float,
    dx: float,
    dy: float,
    nx: int,
    ny: int,
) -> tuple[int, int]:
    x = int(round((lon - lon_min) / dx))
    y = int(round((lat - lat_min) / dy))

    is_global_x = nx * dx >= 359
    is_global_y = ny * dy >= 179

    if is_global_x:
        if x == -1:
            x = 0
        elif x in (nx, nx + 1):
            x = nx - 1
    if is_global_y:
        if y == -1:
            y = 0
        elif y == ny:
            y = ny - 1

    if y < 0 or x < 0 or y >= ny or x >= nx:
        raise ValueError("lat/lon is outside grid bounds")

    return x, y


def main() -> int:
    parser = argparse.ArgumentParser(description="Read OM header and query a single value.")
    parser.add_argument("--file", required=True, help="Path to .om file")
    parser.add_argument("--lat", type=float, required=True, help="Latitude to query")
    parser.add_argument("--lon", type=float, required=True, help="Longitude to query")
    parser.add_argument(
        "--grid",
        choices=("regular", "gaussian"),
        default="regular",
        help="Grid type. regular=regular lat/lon, gaussian=reduced Gaussian grid (ECMWF).",
    )
    parser.add_argument(
        "--gaussian-type",
        choices=tuple(t.value for t in GaussianGridType),
        default=GaussianGridType.O320.value,
        help="Reduced Gaussian grid type (only used when --grid=gaussian).",
    )
    parser.add_argument("--lat-min", type=float, help="Grid latitude minimum (regular grid only)")
    parser.add_argument("--lon-min", type=float, help="Grid longitude minimum (regular grid only)")
    parser.add_argument("--dx", type=float, help="Grid spacing in longitude (regular grid only)")
    parser.add_argument("--dy", type=float, help="Grid spacing in latitude (regular grid only)")

    args = parser.parse_args()

    reader = OmFileReader(args.file)
    dims = get_dimensions(reader)

    if len(dims) < 2:
        raise ValueError(f"Expected at least 2 dimensions, got {dims}")

    ny, nx = dims[0], dims[1]

    print(f"Grid: nx={nx} ny={ny}")
    if args.grid == "regular":
        if args.lat_min is None or args.lon_min is None or args.dx is None or args.dy is None:
            raise ValueError("--lat-min/--lon-min/--dx/--dy are required when --grid=regular")
        lat_max = args.lat_min + args.dy * (ny - 1)
        lon_max = args.lon_min + args.dx * (nx - 1)
        print(
            f"Bounds: latMin={args.lat_min} latMax={lat_max} "
            f"lonMin={args.lon_min} lonMax={lon_max}"
        )
        x, y = find_point_regular(
            lat=args.lat,
            lon=args.lon,
            lat_min=args.lat_min,
            lon_min=args.lon_min,
            dx=args.dx,
            dy=args.dy,
            nx=nx,
            ny=ny,
        )
        index = y * nx + x
        print(f"Point: lat={args.lat} lon={args.lon} -> x={x} y={y} index={index}")
    else:
        # Reduced Gaussian grids in this repository are stored as ny=1, nx=numberOfDataPoints.
        if ny != 1:
            raise ValueError(
                f"Expected ny=1 for reduced Gaussian grid OM, got ny={ny}. "
                "Are you sure this is a Gaussian-grid OM file?"
            )
        grid_type = GaussianGridType(args.gaussian_type)
        if nx != grid_type.count:
            raise ValueError(
                f"Dimensions mismatch: nx={nx}, but {grid_type.value} expects {grid_type.count} points."
            )
        grid = ReducedGaussianGrid(grid_type=grid_type)
        gridpoint = grid.find_point(lat=args.lat, lon=args.lon)
        index = gridpoint  # ny=1, so row-major index equals x coordinate
        print(
            f"Point: lat={args.lat} lon={args.lon} -> gridpoint={gridpoint} index={index} "
            f"(gaussian={grid_type.value})"
        )

    data = read_all(reader)
    value = data[index]
    if isinstance(value, float) and math.isnan(value):
        print("Value: NaN")
    else:
        print(f"Value: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read an OM file header and query a value by lat/lon for a regular grid.

This script expects an OM reader library that exposes a minimal interface:
- OmFileReader(path)
- reader.get_dimensions() -> list/tuple
- reader.read() -> flat list/array

If your library uses different method names, update the helpers below.
"""
from __future__ import annotations

import argparse
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


def round_ties_away_from_zero(value: float) -> int:
    """Round to nearest integer, with half values rounded away from zero.

    This matches Swift's `roundf()` behavior (ties away from zero) and differs
    from Python's built-in `round()` which uses banker's rounding (ties to even).
    """
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


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
    x = round_ties_away_from_zero((lon - lon_min) / dx)
    y = round_ties_away_from_zero((lat - lat_min) / dy)

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
    parser.add_argument("--lat-min", type=float, required=True, help="Grid latitude minimum")
    parser.add_argument("--lon-min", type=float, required=True, help="Grid longitude minimum")
    parser.add_argument("--dx", type=float, required=True, help="Grid spacing in longitude")
    parser.add_argument("--dy", type=float, required=True, help="Grid spacing in latitude")

    args = parser.parse_args()

    reader = OmFileReader(args.file)
    dims = get_dimensions(reader)

    if len(dims) < 2:
        raise ValueError(f"Expected at least 2 dimensions, got {dims}")

    ny, nx = dims[0], dims[1]
    lat_max = args.lat_min + args.dy * (ny - 1)
    lon_max = args.lon_min + args.dx * (nx - 1)

    print(f"Grid: nx={nx} ny={ny}")
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

    data = read_all(reader)
    value = data[index]
    if isinstance(value, float) and math.isnan(value):
        print("Value: NaN")
    else:
        print(f"Value: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

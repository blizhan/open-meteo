# Open-Meteo OM Format Readme (Practical Guide)

This guide summarizes how OM files are used in this repository and provides a Python example that:

1. Reads OM header dimensions (`nx/ny`).
2. Computes `latMin/latMax` and `lonMin/lonMax` from user-supplied grid parameters (required for regular lat/lon grids).
3. Maps a user-provided `lat/lon` to a grid index and reads a single data value.

> **Why do we need grid parameters?**
> The OM files store compressed arrays (dimensions, chunks, compression, scale factor), but **do not encode the model grid definition** (e.g., `latMin/lonMin/dx/dy`). Those parameters are model-specific and live in domain configuration code. The Python example therefore requires you to supply grid parameters explicitly.

## 1) What OM files contain (in this repo)

OM files are written by `OmFileWriter` with array dimensions and compression metadata. The writing path is centralized in `OmFileWriterHelper`, which prepares the array and writes metadata like `forecast_reference_time`, `time`, and `coordinates` where applicable.【F:Sources/App/Helper/OmFileWriterHelper.swift†L6-L146】

When converting data, downloaders follow a **GRIB/NetCDF → array → OM** flow. For example, the MeteoFrance downloader parses GRIB into a 2D array, flips axes when needed, and writes an OM file via `writeOmFile2D(...)`.【F:Sources/App/MeteoFrance/MeteoFranceDownloader.swift†L114-L150】

## 2) Regular grid index formula (lat/lon → index)

For regular lat/lon grids, the repository uses a **row-major index** with rounding and some global-grid edge handling:

- `x = round((lon - lonMin) / dx)`
- `y = round((lat - latMin) / dy)`
- `index = y * nx + x`

This logic is implemented in `RegularGrid.findPointXy` / `findPoint`.【F:Sources/App/Domains/RegularGrid.swift†L43-L88】

> **Note:** For global grids, the Swift implementation allows some wrap/edge cases to keep the index inside `[0, nx/ny)`.

## 3) Python example (read dimensions + value at lat/lon)

The script below expects a Python OM reader library (not included in this repo). It is written to work with a minimal `OmFileReader` interface that exposes:

- `get_dimensions()` (or `.dimensions`) → list of dimension sizes
- `read()` → flat array of values

The example also requires you to pass `latMin/lonMin/dx/dy` so it can compute `latMax/lonMax` and map `lat/lon` to a grid index.

## 4) Where to get grid parameters

OM files only store the array data and compression metadata. The **grid definition** (e.g., `latMin/lonMin/dx/dy` for a regular lat/lon grid) is part of the **domain configuration** in this repository and is not serialized into each OM file. For regular grids, those parameters are initialized on `RegularGrid` and used by `findPoint` to resolve indices.【F:Sources/App/Domains/RegularGrid.swift†L3-L88】

There is a model-level `meta.json` written alongside data, but it currently contains timing metadata and a CRS WKT string, not explicit `latMin/lonMin/dx/dy` bounds.【F:Sources/App/Helper/File/ModelMetaJson.swift†L41-L118】

### Example command

```bash
python examples/om_read_example.py \
  --file data/cmc_gem_gdps/temperature_2m/chunk_0.om \
  --lat 52.52 \
  --lon 13.41 \
  --lat-min -90 \
  --lon-min -180 \
  --dx 0.25 \
  --dy 0.25
```

### Example output (shape + bounds + value)

```
Grid: nx=1440 ny=721
Bounds: latMin=-90 latMax=90 lonMin=-180 lonMax=180
Point: lat=52.52 lon=13.41 -> x=?? y=?? index=??
Value: ...
```

## 5) Python example file

See `examples/om_read_example.py` for the full script.

---

### References (implementation in this repo)

- OM writing logic and metadata: `OmFileWriterHelper`【F:Sources/App/Helper/OmFileWriterHelper.swift†L6-L146】
- Regular grid index mapping: `RegularGrid.findPointXy` / `findPoint`【F:Sources/App/Domains/RegularGrid.swift†L43-L88】
- GRIB → OM conversion example: MeteoFrance downloader【F:Sources/App/MeteoFrance/MeteoFranceDownloader.swift†L114-L150】

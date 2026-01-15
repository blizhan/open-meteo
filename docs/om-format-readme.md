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

## 2b) Reduced Gaussian grid (高斯/减缩高斯网格, ECMWF) → OM

Some ECMWF products in this repository (e.g. IFS / SEAS5 / EC46) are provided on a **reduced Gaussian grid** (`gridType=reduced_gg` in GRIB). In that case, the pipeline is **not** “Gaussian → regrid to regular lat/lon → OM”. Instead, the conversion is:

**GRIB (`reduced_gg`) → flat array in native scan order → OM**

Concretely:

- **No regridding step**: values are loaded from GRIB in the order returned by ecCodes and written as-is to OM.
- **OM dimensions**: the “spatial” axis is treated as a **1D locations axis** with length `numberOfDataPoints`.
  - In code, `GaussianGrid.nx == type.count` and `GaussianGrid.ny == 1`.【F:Sources/App/Domains/GaussianGrid.swift†L49-L61】【F:Sources/App/Domains/GaussianGrid.swift†L136-L141】
  - When reading GRIB, the converter validates `numberOfDataPoints == nx * ny` for `reduced_gg` and then loads values into a flat buffer `array.data[i]` (`i = 0..<count`).【F:Sources/App/Helper/Download/Curl+Grib.swift†L150-L175】
- **Grid definition is not in OM**: for Gaussian grids you cannot derive `latMin/lonMin/dx/dy` from the OM file. The mapping `gridpoint <-> (lat, lon)` depends on the **Gaussian grid type** (e.g. O1280 / O320 / N160) and the repository’s indexing rules.

How the repository indexes a reduced Gaussian grid:

- A single integer `gridpoint` (the OM “location index”) is used.
- The grid is conceptually a set of latitude lines, where each line has its own `nxOf(y)` (number of longitudes), so there is no single global `dx`.
- `gridpoint` is defined as `gridpoint = integral(y) + x`, where `integral(y)` is the prefix-sum of `nxOf` over all latitude lines `< y`.【F:Sources/App/Domains/GaussianGrid.swift†L86-L107】【F:Sources/App/Domains/GaussianGrid.swift†L168-L171】
- Given a `(lat, lon)`, the repository picks the nearest point (no fractional/bilinear position) via `GaussianGrid.findPoint` / `findPointXY`.【F:Sources/App/Domains/GaussianGrid.swift†L146-L201】

Where to get the Gaussian grid type when you only have the OM files:

- The domain-level `meta.json` includes `crs_wkt` (WKT2). For reduced Gaussian grids this project writes an artificial WKT with a `REMARK["Reduced Gaussian Grid O320 (ECMWF)"]` (or similar), so readers can detect the intended Gaussian grid type.【F:Sources/App/Helper/File/ModelMetaJson.swift†L81-L108】【F:Sources/App/Domains/GaussianGrid.swift†L6-L20】

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
  --grid regular \
  --lat-min -90 \
  --lon-min -180 \
  --dx 0.25 \
  --dy 0.25
```

### Example command (Gaussian grid / 高斯网格)

For ECMWF reduced Gaussian grid files written by this repo, the OM array is stored as `ny=1` and `nx=numberOfDataPoints`. The script implements the repository’s nearest-point mapping (`GaussianGrid.findPoint`) for O-type grids.

```bash
python examples/om_read_example.py \
  --file data_spatial/ecmwf_seas5/202501010000/2025-01-01T06:00.om \
  --lat 52.52 \
  --lon 13.41 \
  --grid gaussian \
  --gaussian-type o320
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
- Reduced Gaussian grid indexing: `GaussianGrid`【F:Sources/App/Domains/GaussianGrid.swift†L1-L206】
- GRIB reduced_gg dimensional check + value loading: `GribArray2D.load`【F:Sources/App/Helper/Download/Curl+Grib.swift†L150-L205】

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path
from typing import Iterable, Sequence


SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_50m_admin_0_countries.geojson"
)
SELECTED_ADMIN_NAMES = {"China", "Taiwan", "Hong Kong S.A.R.", "Macao S.A.R"}
MAP_BOUNDS = (70.0, 140.0, 15.0, 55.0)
VIEW_BOUNDS = (54.0, 946.0, 58.0, 648.0)


Point = tuple[float, float]


def _perpendicular_distance(point: Point, start: Point, end: Point) -> float:
    if start == end:
        return math.dist(point, start)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    numerator = abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0])
    return numerator / math.hypot(dx, dy)


def _simplify(points: Sequence[Point], tolerance: float) -> list[Point]:
    if len(points) <= 3:
        return list(points)
    furthest_index = 0
    furthest_distance = 0.0
    for index, point in enumerate(points[1:-1], start=1):
        distance = _perpendicular_distance(point, points[0], points[-1])
        if distance > furthest_distance:
            furthest_distance = distance
            furthest_index = index
    if furthest_distance <= tolerance:
        return [points[0], points[-1]]
    left = _simplify(points[: furthest_index + 1], tolerance)
    right = _simplify(points[furthest_index:], tolerance)
    return left[:-1] + right


def _project(point: Point) -> Point:
    longitude, latitude = point
    min_lon, max_lon, min_lat, max_lat = MAP_BOUNDS
    min_x, max_x, min_y, max_y = VIEW_BOUNDS
    x = min_x + (longitude - min_lon) / (max_lon - min_lon) * (max_x - min_x)
    y = min_y + (max_lat - latitude) / (max_lat - min_lat) * (max_y - min_y)
    return x, y


def _rings(geometry: dict[str, object]) -> Iterable[list[Point]]:
    geometry_type = geometry["type"]
    coordinates = geometry["coordinates"]
    polygons = coordinates if geometry_type == "MultiPolygon" else [coordinates]
    for polygon in polygons:  # type: ignore[assignment]
        for ring in polygon:  # type: ignore[assignment]
            yield [(float(longitude), float(latitude)) for longitude, latitude in ring]


def _ring_path(ring: Sequence[Point]) -> str:
    simplified = _simplify(ring, tolerance=0.075)
    projected = [_project(point) for point in simplified]
    if len(projected) < 3:
        return ""
    commands = [f"M {projected[0][0]:.1f} {projected[0][1]:.1f}"]
    commands.extend(f"L {x:.1f} {y:.1f}" for x, y in projected[1:])
    commands.append("Z")
    return " ".join(commands)


def _load(source: Path | None) -> dict[str, object]:
    if source is not None:
        return json.loads(source.read_text(encoding="utf-8"))
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
        return json.load(response)


def generate(source: Path | None, output: Path) -> None:
    document = _load(source)
    paths: list[str] = []
    for feature in document["features"]:  # type: ignore[index]
        properties = feature["properties"]
        if properties.get("ADMIN") not in SELECTED_ADMIN_NAMES:
            continue
        paths.extend(filter(None, (_ring_path(ring) for ring in _rings(feature["geometry"]))))
    if not paths:
        raise RuntimeError("Natural Earth source did not contain the selected reference features")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "// Generated from Natural Earth 1:50m Admin 0 public-domain data.\n"
        "// This modern outline is a faint geographic reference, never a historical boundary.\n"
        f"export const NATURAL_EARTH_SOURCE = '{SOURCE_URL}';\n"
        f"export const CHINA_REFERENCE_PATH = {json.dumps(' '.join(paths))};\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("apps/web/src/pages/courses/chinaReferencePath.ts"),
    )
    args = parser.parse_args()
    generate(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

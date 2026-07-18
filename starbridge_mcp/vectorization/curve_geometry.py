from __future__ import annotations

import math
from typing import Any

Point = tuple[float, float]


def format_coordinate(value: float) -> str:
    if math.isclose(value, round(value), abs_tol=0.0005):
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def point_text(point: Point) -> str:
    return f"{format_coordinate(point[0])} {format_coordinate(point[1])}"


def interior_angle(previous: Point, current: Point, following: Point) -> float:
    first = (previous[0] - current[0], previous[1] - current[1])
    second = (following[0] - current[0], following[1] - current[1])
    first_length = math.hypot(*first)
    second_length = math.hypot(*second)
    if first_length == 0 or second_length == 0:
        return 0.0
    cosine = (first[0] * second[0] + first[1] * second[1]) / (first_length * second_length)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def unit(vector_x: float, vector_y: float) -> tuple[float, float]:
    length = math.hypot(vector_x, vector_y)
    if length == 0:
        return 0.0, 0.0
    return vector_x / length, vector_y / length


def open_path(
    points: list[Point],
    *,
    corner_angle: float,
    smoothing: float,
) -> tuple[str, dict[str, Any]]:
    tangents: list[tuple[float, float]] = []
    smooth: list[bool] = []
    for index, current in enumerate(points):
        if index == 0:
            tangent = unit(points[1][0] - current[0], points[1][1] - current[1])
            tangents.append(tangent)
            smooth.append(True)
        elif index == len(points) - 1:
            tangent = unit(current[0] - points[index - 1][0], current[1] - points[index - 1][1])
            tangents.append(tangent)
            smooth.append(True)
        else:
            tangent = unit(
                points[index + 1][0] - points[index - 1][0],
                points[index + 1][1] - points[index - 1][1],
            )
            tangents.append(tangent)
            smooth.append(
                interior_angle(points[index - 1], current, points[index + 1]) >= corner_angle
            )

    minimum_x = min(point[0] for point in points)
    maximum_x = max(point[0] for point in points)
    minimum_y = min(point[1] for point in points)
    maximum_y = max(point[1] for point in points)
    commands = [f"M {point_text(points[0])}"]
    sampled = [points[0]]
    curves = 0
    lines = 0
    controls = 0
    for index, current in enumerate(points[:-1]):
        following = points[index + 1]
        chord = math.dist(current, following)
        if chord > 1.0 and (smooth[index] or smooth[index + 1]):
            handle = chord * smoothing / 3.0
            control_1 = (
                max(minimum_x, min(maximum_x, current[0] + tangents[index][0] * handle)),
                max(minimum_y, min(maximum_y, current[1] + tangents[index][1] * handle)),
            )
            control_2 = (
                max(
                    minimum_x,
                    min(maximum_x, following[0] - tangents[index + 1][0] * handle),
                ),
                max(
                    minimum_y,
                    min(maximum_y, following[1] - tangents[index + 1][1] * handle),
                ),
            )
            commands.append(
                f"C {point_text(control_1)} {point_text(control_2)} {point_text(following)}"
            )
            curves += 1
            controls += 2
            for sample_index in range(1, 9):
                t = sample_index / 8.0
                inverse = 1.0 - t
                sampled.append(
                    (
                        inverse**3 * current[0]
                        + 3 * inverse**2 * t * control_1[0]
                        + 3 * inverse * t**2 * control_2[0]
                        + t**3 * following[0],
                        inverse**3 * current[1]
                        + 3 * inverse**2 * t * control_1[1]
                        + 3 * inverse * t**2 * control_2[1]
                        + t**3 * following[1],
                    )
                )
        else:
            commands.append(f"L {point_text(following)}")
            lines += 1
            sampled.append(following)
    return " ".join(commands), {
        "anchors": len(points),
        "control_points": controls,
        "curve_segments": curves,
        "line_segments": lines,
        "corner_anchors": sum(not value for value in smooth),
        "smooth_anchors": sum(smooth),
        "sampled_points": sampled,
    }

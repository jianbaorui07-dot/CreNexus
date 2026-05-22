import math
import pathlib
import time

import pythoncom
import win32com.client


WORKSPACE = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = WORKSPACE / "output" / "connection_plate_1to1.dwg"


def vt_point(point):
    x, y, *rest = point
    z = rest[0] if rest else 0.0
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(x), float(y), float(z)])


def vt_doubles(values):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values])


def connect_autocad():
    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        app = win32com.client.Dispatch("AutoCAD.Application")
        app.Visible = True
        time.sleep(8)

    app.Visible = True
    try:
        doc = app.ActiveDocument
    except Exception:
        doc = app.Documents.Add()
        time.sleep(2)
    return app, doc, doc.ModelSpace


def clear_modelspace(model):
    for index in range(model.Count - 1, -1, -1):
        try:
            model.Item(index).Delete()
        except Exception:
            pass


def ensure_layer(doc, name, color, linetype=None):
    try:
        layer = doc.Layers.Item(name)
    except Exception:
        layer = doc.Layers.Add(name)
    layer.Color = color
    if linetype:
        try:
            layer.Linetype = linetype
        except Exception:
            pass
    return layer


def setup_doc(doc):
    try:
        doc.SetVariable("INSUNITS", 4)  # millimeters
        doc.SetVariable("LUNITS", 2)
        doc.SetVariable("LUPREC", 0)
        doc.SetVariable("AUPREC", 0)
        doc.SetVariable("DIMDEC", 0)
        doc.SetVariable("DIMADEC", 0)
        doc.SetVariable("DIMTXT", 3.0)
        doc.SetVariable("DIMASZ", 2.2)
        doc.SetVariable("DIMSCALE", 1.0)
        doc.SetVariable("LTSCALE", 0.45)
    except Exception:
        pass
    try:
        doc.Linetypes.Load("CENTER", "acad.lin")
    except Exception:
        pass

    ensure_layer(doc, "OUTLINE_THICK", 7)
    ensure_layer(doc, "HOLES_THICK", 7)
    ensure_layer(doc, "CENTER_DASH", 8, "CENTER")
    ensure_layer(doc, "DIM_THIN", 7)
    ensure_layer(doc, "CONSTRUCTION_DASH", 8, "CENTER")


def style(entity, layer, color=7, lineweight=25, linetype=None):
    entity.Layer = layer
    entity.Color = color
    try:
        entity.LineWeight = lineweight
    except Exception:
        pass
    if linetype:
        try:
            entity.Linetype = linetype
        except Exception:
            pass
    return entity


def line(model, p1, p2, layer="OUTLINE_THICK", color=7, lineweight=35, linetype=None):
    return style(model.AddLine(vt_point(p1), vt_point(p2)), layer, color, lineweight, linetype)


def circle(model, center, radius, layer="OUTLINE_THICK", color=7, lineweight=35):
    return style(model.AddCircle(vt_point(center), radius), layer, color, lineweight)


def arc(model, center, radius, start_deg, end_deg, layer="OUTLINE_THICK", color=7, lineweight=35):
    return style(
        model.AddArc(vt_point(center), radius, math.radians(start_deg), math.radians(end_deg)),
        layer,
        color,
        lineweight,
    )


def polyline(model, points, layer="DIM_THIN", color=7, lineweight=15, closed=False, linetype=None):
    coords = []
    for x, y in points:
        coords.extend([x, y])
    entity = model.AddLightWeightPolyline(vt_doubles(coords))
    entity.Closed = bool(closed)
    return style(entity, layer, color, lineweight, linetype)


def text(model, position, value, height=3.2, rotation=0.0, layer="DIM_THIN", color=7):
    entity = model.AddText(value, vt_point(position), height)
    entity.Rotation = math.radians(rotation)
    return style(entity, layer, color, 15)


def dim_aligned(model, p1, p2, text_position, override=None):
    dim = model.AddDimAligned(vt_point(p1), vt_point(p2), vt_point(text_position))
    style(dim, "DIM_THIN", 7, 15)
    if override is not None:
        try:
            dim.TextOverride = override
        except Exception:
            pass
    return dim


def arrowhead(model, tip, angle_deg, size=1.8):
    angle = math.radians(angle_deg)
    for offset in (150, -150):
        a = angle + math.radians(offset)
        end = (tip[0] + size * math.cos(a), tip[1] + size * math.sin(a), 0)
        line(model, tip, end, "DIM_THIN", 7, 15)


def leader(model, tip, elbow, label_position, label, text_rotation=0.0):
    line(model, tip, elbow, "DIM_THIN", 7, 15)
    line(model, elbow, label_position, "DIM_THIN", 7, 15)
    direction = math.degrees(math.atan2(elbow[1] - tip[1], elbow[0] - tip[0]))
    arrowhead(model, tip, direction + 180)
    text(model, label_position, label, 3.2, text_rotation)


def center_cross(model, center, radius, extension=4.0):
    x, y = center
    line(model, (x - radius - extension, y, 0), (x + radius + extension, y, 0), "CENTER_DASH", 8, 15, "CENTER")
    line(model, (x, y - radius - extension, 0), (x, y + radius + extension, 0), "CENTER_DASH", 8, 15, "CENTER")


def tangent_points_same_side(c1, r1, c2, r2):
    dx = c2[0] - c1[0]
    dy = c2[1] - c1[1]
    distance = math.hypot(dx, dy)
    ux, uy = dx / distance, dy / distance
    px, py = -uy, ux
    target = (r2 - r1) / distance
    offset = math.sqrt(max(0.0, 1.0 - target * target))
    tangents = []
    for sign in (1, -1):
        nx = target * ux + sign * offset * px
        ny = target * uy + sign * offset * py
        p1 = (c1[0] - r1 * nx, c1[1] - r1 * ny, 0)
        p2 = (c2[0] - r2 * nx, c2[1] - r2 * ny, 0)
        tangents.append((p1, p2))
    return tangents


def radius_arc_through_points(model, p1, p2, radius, choose_above=True):
    x1, y1 = p1
    x2, y2 = p2
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    dx, dy = x2 - x1, y2 - y1
    chord = math.hypot(dx, dy)
    h = math.sqrt(radius * radius - (chord / 2.0) ** 2)
    ux, uy = -dy / chord, dx / chord
    centers = [(mx + h * ux, my + h * uy), (mx - h * ux, my - h * uy)]
    center = max(centers, key=lambda c: c[1]) if choose_above else min(centers, key=lambda c: c[1])
    a1 = math.degrees(math.atan2(y1 - center[1], x1 - center[0])) % 360
    a2 = math.degrees(math.atan2(y2 - center[1], x2 - center[0])) % 360
    return arc(model, center, radius, a1, a2)


def angle_dimension(model, vertex, radius, start_deg, end_deg, label):
    points = []
    for i in range(36):
        angle = math.radians(start_deg + (end_deg - start_deg) * i / 35.0)
        points.append((vertex[0] + radius * math.cos(angle), vertex[1] + radius * math.sin(angle)))
    polyline(model, points, "DIM_THIN", 7, 15)
    arrowhead(model, (points[0][0], points[0][1], 0), start_deg + 90)
    arrowhead(model, (points[-1][0], points[-1][1], 0), end_deg - 90)
    mid = math.radians((start_deg + end_deg) / 2.0)
    text(model, (vertex[0] + (radius + 4) * math.cos(mid), vertex[1] + (radius + 4) * math.sin(mid), 0), label, 3.2)


def draw_plate():
    app, doc, model = connect_autocad()
    clear_modelspace(model)
    setup_doc(doc)

    # Main dimensions in mm.
    d_big_outer = 44.0
    d_big_inner = 24.0
    d_left_outer = 19.0
    d_left_inner = 11.0
    d_lower_inner = 13.0
    r_lower_outer = 10.0
    d_right_outer = 12.0
    d_right_inner = 8.0
    center_distance_top = 41.0
    lower_to_big_horizontal = 40.0
    left_vertical_distance = 26.0
    top_step = 7.0
    lower_right_distance = 39.0
    lower_right_angle = 69.0
    r_inner_transition = 80.0

    # Coordinate basis: left upper hole center is origin.
    left_top = (0.0, 0.0)
    big = (center_distance_top, 0.0)
    lower_left = (big[0] - lower_to_big_horizontal, -left_vertical_distance)
    right_lower = (
        big[0] + lower_right_distance * math.cos(math.radians(lower_right_angle)),
        big[1] - lower_right_distance * math.sin(math.radians(lower_right_angle)),
    )

    r_left_outer = d_left_outer / 2.0
    r_left_inner = d_left_inner / 2.0
    r_big_outer = d_big_outer / 2.0
    r_big_inner = d_big_inner / 2.0
    r_lower_inner = d_lower_inner / 2.0
    r_right_outer = d_right_outer / 2.0
    r_right_inner = d_right_inner / 2.0

    # Holes and bosses.
    circle(model, big, r_big_outer)
    circle(model, big, r_big_inner, "HOLES_THICK")
    circle(model, left_top, r_left_outer)
    circle(model, left_top, r_left_inner, "HOLES_THICK")
    circle(model, lower_left, r_lower_inner, "HOLES_THICK")
    circle(model, right_lower, r_right_outer)
    circle(model, right_lower, r_right_inner, "HOLES_THICK")

    # Tangent / outline construction.
    shoulder_y = top_step
    left_top_tangent_x = math.sqrt(r_left_outer**2 - shoulder_y**2)
    big_top_tangent_x = big[0] - math.sqrt(r_big_outer**2 - shoulder_y**2)
    line(model, (left_top_tangent_x, shoulder_y, 0), (big_top_tangent_x, shoulder_y, 0))

    left_side_x = lower_left[0] - r_lower_outer
    line(model, (left_side_x, left_top[1], 0), (left_side_x, lower_left[1], 0))
    arc(model, lower_left, r_lower_outer, 180, 270)
    bottom_y = lower_left[1] - r_lower_outer
    line(model, (lower_left[0], bottom_y, 0), (big[0], bottom_y, 0))

    right_tangents = tangent_points_same_side(big, r_big_outer, right_lower, r_right_outer)
    # The nearly vertical tangent is the outer right boundary; the diagonal one is the lower inner boundary.
    right_tangent = min(right_tangents, key=lambda pair: abs(pair[0][0] - pair[1][0]))
    lower_diagonal = max(right_tangents, key=lambda pair: abs(pair[0][0] - pair[1][0]))
    line(model, right_tangent[0], right_tangent[1])
    line(model, lower_diagonal[0], lower_diagonal[1])

    # R80 inner concave transition.
    r80_start_angle_on_left_top = -52.0
    r80_end_angle_on_right_lower = 135.0
    r80_start = (
        left_top[0] + r_left_outer * math.cos(math.radians(r80_start_angle_on_left_top)),
        left_top[1] + r_left_outer * math.sin(math.radians(r80_start_angle_on_left_top)),
    )
    r80_end = (
        right_lower[0] + r_right_outer * math.cos(math.radians(r80_end_angle_on_right_lower)),
        right_lower[1] + r_right_outer * math.sin(math.radians(r80_end_angle_on_right_lower)),
    )
    radius_arc_through_points(model, r80_start, r80_end, r_inner_transition, choose_above=True)

    # Center lines.
    center_cross(model, left_top, r_left_outer)
    center_cross(model, big, r_big_outer)
    center_cross(model, lower_left, r_lower_outer)
    center_cross(model, right_lower, r_right_outer)
    line(model, (left_top[0] - 17, 0, 0), (big[0] + 49, 0, 0), "CENTER_DASH", 8, 15, "CENTER")
    line(model, (big[0], 30, 0), (big[0], -52, 0), "CENTER_DASH", 8, 15, "CENTER")
    line(model, (big[0], big[1], 0), (right_lower[0], right_lower[1], 0), "CONSTRUCTION_DASH", 8, 15, "CENTER")

    # Position dimensions.
    dim_aligned(model, (left_top[0], 29, 0), (big[0], 29, 0), ((left_top[0] + big[0]) / 2, 35, 0), "41")
    line(model, (left_top[0], r_left_outer, 0), (left_top[0], 32, 0), "DIM_THIN", 7, 15)
    line(model, (big[0], r_big_outer, 0), (big[0], 32, 0), "DIM_THIN", 7, 15)

    dim_aligned(model, (lower_left[0], -51, 0), (big[0], -51, 0), ((lower_left[0] + big[0]) / 2, -57, 0), "40")
    line(model, (lower_left[0], bottom_y, 0), (lower_left[0], -54, 0), "DIM_THIN", 7, 15)
    line(model, (big[0], bottom_y, 0), (big[0], -54, 0), "DIM_THIN", 7, 15)

    dim_aligned(model, (-23, left_top[1], 0), (-23, lower_left[1], 0), (-29, (left_top[1] + lower_left[1]) / 2, 0), "26")
    line(model, (left_side_x, left_top[1], 0), (-25, left_top[1], 0), "DIM_THIN", 7, 15)
    line(model, (left_side_x, lower_left[1], 0), (-25, lower_left[1], 0), "DIM_THIN", 7, 15)

    dim_aligned(model, (-23, shoulder_y, 0), (-23, left_top[1], 0), (-29, shoulder_y / 2, 0), "7")
    line(model, (left_side_x, shoulder_y, 0), (-25, shoulder_y, 0), "DIM_THIN", 7, 15)

    dim_aligned(model, (big[0], big[1], 0), (right_lower[0], right_lower[1], 0), (66, -18, 0), "39")
    angle_dimension(model, right_lower, 34, 0, lower_right_angle, "69%%d")

    # Diameter and radius callouts.
    leader(model, (big[0] + 15.6, big[1] + 15.4, 0), (55, 25, 0), (58, 26, 0), "%%c44")
    leader(model, (big[0] - 5.0, big[1] + 10.9, 0), (24, 13.5, 0), (26, 15, 0), "%%c24")
    leader(model, (left_top[0] - 2.8, left_top[1] + 9.0, 0), (-6, 18, 0), (-14, 18, 0), "%%c19")
    leader(model, (left_top[0] - 3.5, left_top[1] + 4.2, 0), (-14, 9, 0), (-19, 9, 0), "%%c11")
    leader(model, (lower_left[0] - 3.5, lower_left[1] - 5.5, 0), (-9, -40, 0), (-16, -40, 0), "%%c13")
    leader(model, (lower_left[0] - 7.1, lower_left[1] - 7.1, 0), (-12, -33, 0), (-20, -33, 0), "R10")
    leader(model, (28, -21, 0), (22, -23, 0), (16, -23, 0), "R80")
    leader(model, (right_lower[0] - 4.3, right_lower[1] - 4.2, 0), (50, -50, 0), (46, -50, 0), "%%c12")
    leader(model, (right_lower[0] + 3.1, right_lower[1] + 2.5, 0), (63, -35, 0), (66, -35, 0), "%%c8")

    try:
        app.ZoomExtents()
    except Exception:
        doc.SendCommand("_.ZOOM _E ")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    try:
        if OUTPUT.exists() and doc.FullName.lower() != str(OUTPUT).lower():
            OUTPUT.unlink()
    except Exception:
        pass
    doc.SaveAs(str(OUTPUT))

    return {
        "document": doc.Name,
        "output": str(OUTPUT),
        "modelspace_count": model.Count,
        "centers": {
            "left_top": left_top,
            "big": big,
            "lower_left": lower_left,
            "right_lower": right_lower,
        },
    }


if __name__ == "__main__":
    result = draw_plate()
    for key, value in result.items():
        print(f"{key}={value}")

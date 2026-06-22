import math
import pathlib
import time

import pythoncom
import win32com.client

WORKSPACE = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = WORKSPACE / "output" / "reference_mechanical_part.dwg"


def vt_point(point):
    x, y, *rest = point
    z = rest[0] if rest else 0.0
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(x), float(y), float(z)]
    )


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
    # Delete from the end because AutoCAD COM collections are live collections.
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


def setup_layers(doc):
    try:
        doc.Linetypes.Load("CENTER", "acad.lin")
    except Exception:
        pass
    ensure_layer(doc, "PART_OUTLINE", 7)
    ensure_layer(doc, "PART_CENTER", 8, "CENTER")
    ensure_layer(doc, "PART_DIM", 7)
    ensure_layer(doc, "PART_CONSTRUCTION", 8, "CENTER")
    ensure_layer(doc, "PART_CN_LABEL", 3)


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


def line(model, p1, p2, layer="PART_OUTLINE", color=7, lineweight=25, linetype=None):
    return style(model.AddLine(vt_point(p1), vt_point(p2)), layer, color, lineweight, linetype)


def circle(model, center, radius, layer="PART_OUTLINE", color=7, lineweight=35):
    return style(model.AddCircle(vt_point(center), radius), layer, color, lineweight)


def arc(model, center, radius, start_deg, end_deg, layer="PART_OUTLINE", color=7, lineweight=35):
    return style(
        model.AddArc(vt_point(center), radius, math.radians(start_deg), math.radians(end_deg)),
        layer,
        color,
        lineweight,
    )


def lwpoly(
    model, points, closed=False, layer="PART_OUTLINE", color=7, lineweight=25, linetype=None
):
    coords = []
    for x, y in points:
        coords.extend([x, y])
    obj = model.AddLightWeightPolyline(vt_doubles(coords))
    obj.Closed = bool(closed)
    return style(obj, layer, color, lineweight, linetype)


def text(model, position, content, height=3.2, layer="PART_DIM", color=7, rotation=0.0):
    obj = model.AddText(content, vt_point(position), height)
    obj.Rotation = math.radians(rotation)
    return style(obj, layer, color, 25)


def dim_aligned(model, p1, p2, text_position, layer="PART_DIM"):
    obj = model.AddDimAligned(vt_point(p1), vt_point(p2), vt_point(text_position))
    return style(obj, layer, 7, 25)


def arrowhead(model, tip, angle_deg, size=1.6, layer="PART_DIM"):
    angle = math.radians(angle_deg)
    for delta in (150, -150):
        a = angle + math.radians(delta)
        p2 = (tip[0] + size * math.cos(a), tip[1] + size * math.sin(a), 0)
        line(model, tip, p2, layer, 7, 15)


def leader(model, start, elbow, label_pos, label, rotation=0):
    line(model, start, elbow, "PART_DIM", 7, 15)
    line(model, elbow, label_pos, "PART_DIM", 7, 15)
    angle = math.degrees(math.atan2(elbow[1] - start[1], elbow[0] - start[0]))
    arrowhead(model, start, angle + 180, 1.5, "PART_DIM")
    text(model, label_pos, label, 3.3, "PART_DIM", 7, rotation)


def cn_label(model, start, elbow, label_pos, label):
    line(model, start, elbow, "PART_CN_LABEL", 3, 15)
    line(model, elbow, label_pos, "PART_CN_LABEL", 3, 15)
    angle = math.degrees(math.atan2(elbow[1] - start[1], elbow[0] - start[0]))
    arrowhead(model, start, angle + 180, 1.5, "PART_CN_LABEL")
    text(model, label_pos, label, 3.4, "PART_CN_LABEL", 3)


def draw_center_cross(model, center, radius, extra=4):
    x, y = center
    line(
        model,
        (x - radius - extra, y, 0),
        (x + radius + extra, y, 0),
        "PART_CENTER",
        8,
        15,
        "CENTER",
    )
    line(
        model,
        (x, y - radius - extra, 0),
        (x, y + radius + extra, 0),
        "PART_CENTER",
        8,
        15,
        "CENTER",
    )


def draw_angle_dimension(model, vertex, radius, start_deg, end_deg, label):
    # Approximate the angular dimension arc with a lightweight polyline.
    pts = []
    for i in range(25):
        t = start_deg + (end_deg - start_deg) * i / 24
        pts.append(
            (
                vertex[0] + radius * math.cos(math.radians(t)),
                vertex[1] + radius * math.sin(math.radians(t)),
            )
        )
    lwpoly(model, pts, False, "PART_DIM", 7, 15)
    arrowhead(model, pts[0] + (0,), start_deg + 90, 1.3, "PART_DIM")
    arrowhead(model, pts[-1] + (0,), end_deg - 90, 1.3, "PART_DIM")
    mid = (start_deg + end_deg) / 2
    text(
        model,
        (
            vertex[0] + (radius + 3) * math.cos(math.radians(mid)),
            vertex[1] + (radius + 3) * math.sin(math.radians(mid)),
            0,
        ),
        label,
        3.4,
    )


def draw():
    app, doc, model = connect_autocad()
    clear_modelspace(model)
    setup_layers(doc)

    # Main geometry in millimeters, following the reference dimensions.
    upper_left = (0.0, 0.0)
    large = (41.0, 0.0)
    lower_left = (1.0, -26.0)
    right_lower = (
        large[0] + 39.0 * math.cos(math.radians(69.0)),
        large[1] - 39.0 * math.sin(math.radians(69.0)),
    )

    r_upper_outer = 19.0 / 2.0
    r_upper_inner = 11.0 / 2.0
    r_large_outer = 44.0 / 2.0
    r_large_inner = 24.0 / 2.0
    r_lower_left_corner = 10.0
    r_lower_left_hole = 13.0 / 2.0
    r_right_outer = 12.0 / 2.0
    r_right_inner = 8.0 / 2.0

    # Circles and holes.
    circle(model, upper_left, r_upper_outer)
    circle(model, upper_left, r_upper_inner)
    circle(model, large, r_large_outer)
    circle(model, large, r_large_inner)
    circle(model, lower_left, r_lower_left_hole)
    circle(model, right_lower, r_right_outer)
    circle(model, right_lower, r_right_inner)

    # Visible outline connections.
    shoulder_y = 7.0
    left_shoulder_x = math.sqrt(r_upper_outer**2 - shoulder_y**2)
    big_shoulder_x = large[0] - math.sqrt(r_large_outer**2 - shoulder_y**2)
    line(model, (left_shoulder_x, shoulder_y, 0), (big_shoulder_x, shoulder_y, 0), lineweight=35)

    left_wall_x = lower_left[0] - r_lower_left_corner
    line(model, (left_wall_x, -26.0, 0), (left_wall_x, 0.0, 0), lineweight=35)
    arc(model, lower_left, r_lower_left_corner, 180, 270)
    bottom_y = lower_left[1] - r_lower_left_corner
    line(model, (lower_left[0], bottom_y, 0), (large[0], bottom_y, 0), lineweight=35)

    # Two tangent lines between the large ring and the lower-right boss.
    line(model, (62.97, -1.22, 0), (60.99, -36.74, 0), lineweight=35)
    line(model, (25.51, -15.62, 0), (50.78, -40.67, 0), lineweight=35)

    # R80 curved lower edge, exact radius through two visually matching tangent points.
    arc(model, (68.2705091614, 45.6385527314), 80.0, 220.0145340442, 256.6510330969, lineweight=35)

    # Center lines.
    for center, rad in [
        (upper_left, r_upper_outer),
        (large, r_large_outer),
        (lower_left, r_lower_left_corner),
        (right_lower, r_right_outer),
    ]:
        draw_center_cross(model, center, rad)
    line(
        model,
        (upper_left[0] - 17, upper_left[1], 0),
        (large[0] + 32, large[1], 0),
        "PART_CENTER",
        8,
        15,
        "CENTER",
    )
    line(
        model,
        (large[0], large[1], 0),
        (right_lower[0], right_lower[1], 0),
        "PART_CONSTRUCTION",
        8,
        15,
        "CENTER",
    )
    line(model, (large[0], 29, 0), (large[0], -48, 0), "PART_CENTER", 8, 15, "CENTER")

    # Linear and aligned dimensions.
    dim_aligned(
        model, (upper_left[0], 28, 0), (large[0], 28, 0), ((upper_left[0] + large[0]) / 2, 33, 0)
    )
    line(model, (upper_left[0], r_upper_outer, 0), (upper_left[0], 31, 0), "PART_DIM", 7, 15)
    line(model, (large[0], r_large_outer, 0), (large[0], 31, 0), "PART_DIM", 7, 15)

    dim_aligned(
        model, (lower_left[0], -50, 0), (large[0], -50, 0), ((lower_left[0] + large[0]) / 2, -55, 0)
    )
    line(model, (lower_left[0], bottom_y, 0), (lower_left[0], -52, 0), "PART_DIM", 7, 15)
    line(model, (large[0], bottom_y, 0), (large[0], -52, 0), "PART_DIM", 7, 15)

    dim_aligned(model, (-21, upper_left[1], 0), (-21, lower_left[1], 0), (-27, -13, 0))
    line(model, (-10, upper_left[1], 0), (-23, upper_left[1], 0), "PART_DIM", 7, 15)
    line(model, (-10, lower_left[1], 0), (-23, lower_left[1], 0), "PART_DIM", 7, 15)

    dim_aligned(model, (-21, shoulder_y, 0), (-21, upper_left[1], 0), (-27, 3.5, 0))
    line(model, (-9, shoulder_y, 0), (-23, shoulder_y, 0), "PART_DIM", 7, 15)

    dim_aligned(model, (large[0], large[1], 0), (right_lower[0], right_lower[1], 0), (65, -18, 0))
    draw_angle_dimension(model, right_lower, 32, 0, 69, "69%%d")

    # Diameter, radius, and callout labels.
    leader(model, (large[0] + 15.0, large[1] + 16.0, 0), (55, 24, 0), (58, 25, 0), "%%c44")
    leader(model, (large[0] - 5.0, large[1] + 10.9, 0), (24, 13, 0), (26, 14, 0), "%%c24")
    leader(model, (upper_left[0] - 3, upper_left[1] + 9.0, 0), (-6, 18, 0), (-14, 18, 0), "%%c19")
    leader(model, (upper_left[0] - 4, upper_left[1] + 4.0, 0), (-14, 8, 0), (-19, 8, 0), "%%c11")
    leader(
        model, (lower_left[0] - 3.5, lower_left[1] - 5.4, 0), (-9, -39, 0), (-16, -39, 0), "%%c13"
    )
    leader(
        model, (lower_left[0] - 7.0, lower_left[1] - 7.0, 0), (-12, -32, 0), (-20, -32, 0), "R10"
    )
    leader(model, (30, -22, 0), (23, -22, 0), (16, -22, 0), "R80")
    leader(
        model, (right_lower[0] - 4.4, right_lower[1] - 4.1, 0), (50, -49, 0), (46, -49, 0), "%%c12"
    )
    leader(
        model, (right_lower[0] + 3.0, right_lower[1] + 2.6, 0), (62, -35, 0), (65, -35, 0), "%%c8"
    )

    # Chinese labels make every functional area clear in the generated DWG.
    text(model, (-24, 44, 0), "参考机械零件示例（单位：mm）", 4.5, "PART_CN_LABEL", 3)
    text(
        model,
        (-24, 39, 0),
        "区域标注：孔位、轮廓、中心线和尺寸均为公开演示",
        3.2,
        "PART_CN_LABEL",
        3,
    )
    cn_label(
        model,
        (large[0] + 9, large[1] + 7, 0),
        (72, 16, 0),
        (76, 16, 0),
        "大圆基准区：外圆 %%c44 / 内孔 %%c24",
    )
    cn_label(
        model,
        (upper_left[0] - 4, upper_left[1] + 4, 0),
        (-35, 17, 0),
        (-58, 17, 0),
        "左上安装孔区：%%c19 / %%c11",
    )
    cn_label(
        model,
        (lower_left[0] - 5, lower_left[1] - 5, 0),
        (-35, -45, 0),
        (-58, -45, 0),
        "左下圆角孔区：%%c13，圆角 R10",
    )
    cn_label(
        model,
        (right_lower[0] + 3, right_lower[1] + 3, 0),
        (77, -35, 0),
        (82, -35, 0),
        "右下小孔区：%%c12 / %%c8",
    )
    cn_label(model, (30, -22, 0), (11, -18, 0), (-18, -18, 0), "下侧轮廓区：R80 过渡圆弧")
    cn_label(model, (large[0], 0, 0), (68, 5, 0), (76, 5, 0), "中心线基准区：孔距 41、角度 69%%d")

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
    return doc, OUTPUT, model.Count


if __name__ == "__main__":
    document, output, count = draw()
    print(f"当前图纸：{document.Name}")
    print(f"输出文件：{output}")
    print(f"图元数量：{count}")

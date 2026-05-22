import math
import pathlib
import time

import pythoncom
import win32com.client


WORKSPACE = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = WORKSPACE / "output" / "girl_holding_rose.dwg"


def vt_point(point):
    x, y, *rest = point
    z = rest[0] if rest else 0
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [x, y, z])


def vt_doubles(values):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, values)


def connect_autocad():
    pythoncom.CoInitialize()
    try:
        app = win32com.client.GetActiveObject("AutoCAD.Application")
    except Exception:
        app = win32com.client.Dispatch("AutoCAD.Application")
        app.Visible = True
        time.sleep(8)

    app.Visible = True
    doc = app.Documents.Add()
    time.sleep(2)
    return app, doc, doc.ModelSpace


def ensure_layer(doc, name, color):
    try:
        layer = doc.Layers.Item(name)
    except Exception:
        layer = doc.Layers.Add(name)
    layer.Color = color
    return layer


def style(entity, layer, color=None, lineweight=25):
    entity.Layer = layer
    if color is not None:
        entity.Color = color
    try:
        entity.LineWeight = lineweight
    except Exception:
        pass
    return entity


def lwpoly(model, points, layer, color=None, closed=False, lineweight=25):
    coords = []
    for x, y in points:
        coords.extend([float(x), float(y)])
    obj = model.AddLightWeightPolyline(vt_doubles(coords))
    obj.Closed = bool(closed)
    return style(obj, layer, color, lineweight)


def line(model, p1, p2, layer, color=None, lineweight=25):
    obj = model.AddLine(vt_point(p1), vt_point(p2))
    return style(obj, layer, color, lineweight)


def circle(model, center, radius, layer, color=None, lineweight=25):
    obj = model.AddCircle(vt_point(center), radius)
    return style(obj, layer, color, lineweight)


def ellipse(model, center, major_axis, ratio, layer, color=None, lineweight=25):
    obj = model.AddEllipse(vt_point(center), vt_point(major_axis), ratio)
    return style(obj, layer, color, lineweight)


def text(model, position, content, height, layer, color=None):
    obj = model.AddText(content, vt_point(position), height)
    return style(obj, layer, color, 25)


def bezier(points, steps=36):
    def interp(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    out = []
    for i in range(steps + 1):
        t = i / steps
        work = list(points)
        while len(work) > 1:
            work = [interp(work[j], work[j + 1], t) for j in range(len(work) - 1)]
        out.append(work[0])
    return out


def add_curve(model, points, layer, color=None, lineweight=25, steps=40):
    return lwpoly(model, bezier(points, steps=steps), layer, color, False, lineweight)


def petal(model, cx, cy, angle_deg, length, width, layer):
    angle = math.radians(angle_deg)
    tip = (cx + math.cos(angle) * length, cy + math.sin(angle) * length)
    left = (
        cx + math.cos(angle + math.pi / 2) * width,
        cy + math.sin(angle + math.pi / 2) * width,
    )
    right = (
        cx + math.cos(angle - math.pi / 2) * width,
        cy + math.sin(angle - math.pi / 2) * width,
    )
    pts = [left]
    pts.extend(bezier([left, tip, right], steps=12)[1:])
    pts.extend(bezier([right, (cx, cy), left], steps=12)[1:])
    return lwpoly(model, pts, layer, 1, True, 25)


def solid_hatch(model, boundary, layer, color):
    try:
        hatch = model.AddHatch(0, "SOLID", True)
        loop = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [boundary])
        hatch.AppendOuterLoop(loop)
        hatch.Evaluate()
        return style(hatch, layer, color, 25)
    except Exception:
        return None


def draw():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    app, doc, model = connect_autocad()

    layers = {
        "OUTLINE": 7,
        "HAIR": 250,
        "SKIN": 30,
        "DRESS": 5,
        "DRESS_DETAIL": 6,
        "ROSE": 1,
        "STEM": 3,
        "DETAIL": 2,
    }
    for name, color in layers.items():
        ensure_layer(doc, name, color)

    outline = "OUTLINE"
    hair = "HAIR"
    skin = "SKIN"
    dress = "DRESS"
    dress_detail = "DRESS_DETAIL"
    rose = "ROSE"
    stem = "STEM"
    detail = "DETAIL"

    # Body and dress.
    skirt = lwpoly(model, [(-42, 42), (-27, 98), (-13, 108), (13, 108), (27, 98), (42, 42)], dress, 5, True, 35)
    solid_hatch(model, skirt, dress, 5)
    lwpoly(model, [(-24, 97), (0, 84), (24, 97)], dress_detail, 6, False, 25)
    lwpoly(model, [(-28, 77), (-12, 69), (0, 76), (12, 69), (28, 77)], dress_detail, 6, False, 20)
    line(model, (-20, 42), (-15, 16), outline, 7, 25)
    line(model, (-5, 42), (-4, 16), outline, 7, 25)
    line(model, (5, 42), (4, 16), outline, 7, 25)
    line(model, (20, 42), (15, 16), outline, 7, 25)
    lwpoly(model, [(-23, 15), (-9, 15), (-7, 10), (-25, 10)], outline, 7, True, 25)
    lwpoly(model, [(7, 15), (23, 15), (25, 10), (6, 10)], outline, 7, True, 25)

    # Neck, face, and hair.
    line(model, (-8, 105), (-8, 96), skin, 30, 25)
    line(model, (8, 105), (8, 96), skin, 30, 25)
    ellipse(model, (0, 128, 0), (0, 18, 0), 0.72, skin, 30, 35)
    add_curve(model, [(-19, 143), (-26, 160), (-6, 170), (14, 160), (20, 143)], hair, 250, 40)
    add_curve(model, [(-19, 143), (-27, 127), (-18, 108), (-4, 111)], hair, 250, 40)
    add_curve(model, [(20, 143), (29, 126), (20, 108), (7, 111)], hair, 250, 40)
    add_curve(model, [(-13, 151), (-7, 142), (1, 139), (10, 151)], hair, 250, 25)
    add_curve(model, [(-24, 134), (-35, 126), (-26, 114), (-32, 104)], hair, 250, 25)
    add_curve(model, [(25, 132), (34, 124), (27, 114), (33, 104)], hair, 250, 25)
    line(model, (-7, 132), (-3, 132), outline, 7, 20)
    line(model, (4, 132), (8, 132), outline, 7, 20)
    add_curve(model, [(-6, 122), (-2, 118), (5, 122)], outline, 7, 20, steps=16)

    # Arms and hands.
    add_curve(model, [(-25, 98), (-42, 89), (-52, 74), (-60, 64)], skin, 30, 30)
    add_curve(model, [(-20, 93), (-36, 84), (-45, 70), (-52, 59)], skin, 30, 30)
    circle(model, (-57, 61, 0), 4.0, skin, 30, 25)

    add_curve(model, [(23, 98), (32, 92), (38, 84), (45, 80)], skin, 30, 30)
    add_curve(model, [(15, 91), (28, 86), (36, 78), (44, 76)], skin, 30, 30)
    circle(model, (45, 78, 0), 4.2, skin, 30, 25)
    line(model, (42, 78), (47, 78), outline, 7, 15)

    # Rose stem, leaves, and flower.
    line(model, (45, 79), (61, 123), stem, 3, 35)
    leaf1 = lwpoly(model, [(52, 99), (42, 104), (51, 107)], stem, 3, True, 20)
    leaf2 = lwpoly(model, [(55, 108), (66, 113), (57, 116)], stem, 3, True, 20)
    solid_hatch(model, leaf1, stem, 3)
    solid_hatch(model, leaf2, stem, 3)
    for angle in [90, 30, -30, -90, 155, 205]:
        petal(model, 61, 126, angle, 8, 4, rose)
    circle(model, (61, 126, 0), 3.0, rose, 1, 25)
    add_curve(model, [(55, 128), (60, 134), (68, 128)], rose, 1, 25, steps=18)
    add_curve(model, [(54, 124), (61, 118), (69, 124)], rose, 1, 25, steps=18)

    # Extra silhouette and caption.
    add_curve(model, [(-42, 42), (-52, 66), (-40, 94), (-23, 104)], outline, 7, 20)
    add_curve(model, [(42, 42), (52, 66), (40, 94), (23, 104)], outline, 7, 20)
    text(model, (-48, 0, 0), "Girl holding a rose", 6, detail, 2)

    try:
        app.ZoomExtents()
    except Exception:
        doc.SendCommand("_.ZOOM _E ")

    doc.SaveAs(str(OUTPUT))
    return OUTPUT


if __name__ == "__main__":
    path = draw()
    print(path)

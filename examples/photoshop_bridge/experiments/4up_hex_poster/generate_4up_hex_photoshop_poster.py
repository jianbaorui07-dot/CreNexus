from __future__ import annotations

import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "photoshop_4up_hex_automation"
TEMPLATE_DIR = WORK / "templates"

DOC_NAME = "4联科技六边形几何海报_自动化分层源文件"
PSD_NAME = "4联科技六边形几何海报_高级分层源文件.psd"
WHITE_PNG_NAME = "4联科技六边形几何海报_白底高清.png"
TRANSPARENT_PNG_NAME = "4联科技六边形几何海报_透明底高清.png"
JPG_NAME = "4联科技六边形几何海报_预览.jpg"

WIDTH = 8360
HEIGHT = 2820
DPI = 300
POSTER_W = 1920
POSTER_H = 2500
MARGIN = 160
GAP = 120
SAFE = 120
SEED = 20260528

COLORS = {
    "deep": "#003A8C",
    "tech": "#007BFF",
    "sky": "#5EC9FF",
    "ice": "#CDEFFF",
    "pale": "#EEF8FF",
    "white": "#FFFFFF",
}

POSTERS = [
    {
        "idx": 1,
        "name": "01_高密集辉光六边形海报",
        "x": 160,
        "y": 160,
        "kind": "dense_glow",
    },
    {
        "idx": 2,
        "name": "02_极简留白六边形海报",
        "x": 2200,
        "y": 160,
        "kind": "minimal_white",
    },
    {
        "idx": 3,
        "name": "03_数据链路六边形海报",
        "x": 4240,
        "y": 160,
        "kind": "data_flow",
    },
    {
        "idx": 4,
        "name": "04_对角散点六边形海报",
        "x": 6280,
        "y": 160,
        "kind": "diagonal_scatter",
    },
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def js_path(path: Path) -> str:
    return path.resolve().as_posix()


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_rgb(a: str, b: str, t: float) -> str:
    ar, ag, ab = hex_to_rgb(a)
    br, bg, bb = hex_to_rgb(b)
    return rgb_to_hex((round(lerp(ar, br, t)), round(lerp(ag, bg, t)), round(lerp(ab, bb, t))))


def hex_points(
    cx: float, cy: float, r: float, rotation: float = math.pi / 6
) -> list[tuple[float, float]]:
    return [
        (
            cx + math.cos(rotation + i * math.tau / 6) * r,
            cy + math.sin(rotation + i * math.tau / 6) * r,
        )
        for i in range(6)
    ]


def svg_polygon(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def write_template_svgs() -> dict[str, Path]:
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    cx = cy = 180
    r = 150
    outer = svg_polygon(hex_points(cx, cy, r))
    inner = svg_polygon(hex_points(cx, cy, r * 0.66))
    small_outer = svg_polygon(hex_points(cx, cy, 64))

    templates: dict[str, str] = {
        "Hex_DeepBlue_Solid": f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">
  <defs>
    <filter id="softGlow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="10" result="blur"/>
      <feColorMatrix in="blur" type="matrix" values="0 0 0 0 0.368 0 0 0 0 0.788 0 0 0 0 1 0 0 0 .45 0"/>
      <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <polygon points="{outer}" fill="{COLORS["deep"]}" opacity=".85" filter="url(#softGlow)"/>
  <polyline points="{outer}" fill="none" stroke="{COLORS["sky"]}" stroke-width="5" opacity=".34" stroke-linejoin="round"/>
</svg>
""",
        "Hex_TechBlue_Solid": f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{COLORS["sky"]}" stop-opacity=".70"/>
      <stop offset=".55" stop-color="{COLORS["tech"]}" stop-opacity=".70"/>
      <stop offset="1" stop-color="{COLORS["deep"]}" stop-opacity=".62"/>
    </linearGradient>
    <filter id="innerEdge" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="1.2"/>
    </filter>
  </defs>
  <polygon points="{outer}" fill="url(#g)" opacity=".70"/>
  <polygon points="{inner}" fill="none" stroke="{COLORS["ice"]}" stroke-width="3" opacity=".24" filter="url(#innerEdge)"/>
  <polyline points="{outer}" fill="none" stroke="{COLORS["sky"]}" stroke-width="4" opacity=".42" stroke-linejoin="round"/>
</svg>
""",
        "Hex_Ice_Transparent": f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">
  <defs>
    <linearGradient id="ice" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{COLORS["white"]}" stop-opacity=".45"/>
      <stop offset=".56" stop-color="{COLORS["ice"]}" stop-opacity=".30"/>
      <stop offset="1" stop-color="{COLORS["sky"]}" stop-opacity=".14"/>
    </linearGradient>
  </defs>
  <polygon points="{outer}" fill="url(#ice)" opacity=".82"/>
  <polyline points="{outer}" fill="none" stroke="{COLORS["white"]}" stroke-width="5" opacity=".70" stroke-linejoin="round"/>
  <polyline points="{inner}" fill="none" stroke="{COLORS["sky"]}" stroke-width="2" opacity=".16" stroke-linejoin="round"/>
</svg>
""",
        "Hex_Outline_Frame": f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">
  <defs>
    <filter id="lineGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <polyline points="{outer}" fill="none" stroke="{COLORS["sky"]}" stroke-width="5" opacity=".62" stroke-linejoin="round" filter="url(#lineGlow)"/>
  <polyline points="{inner}" fill="none" stroke="{COLORS["ice"]}" stroke-width="2" opacity=".26" stroke-linejoin="round"/>
</svg>
""",
        "Hex_Micro_Particle": f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">
  <polygon points="{small_outer}" fill="{COLORS["sky"]}" opacity=".38"/>
  <polyline points="{small_outer}" fill="none" stroke="{COLORS["ice"]}" stroke-width="3" opacity=".55" stroke-linejoin="round"/>
</svg>
""",
        "Hex_Glass_Glow": f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">
  <defs>
    <radialGradient id="glass" cx=".35" cy=".28" r=".86">
      <stop offset="0" stop-color="{COLORS["white"]}" stop-opacity=".68"/>
      <stop offset=".44" stop-color="{COLORS["ice"]}" stop-opacity=".36"/>
      <stop offset="1" stop-color="{COLORS["tech"]}" stop-opacity=".18"/>
    </radialGradient>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="5" result="blur"/>
      <feColorMatrix in="blur" type="matrix" values="0 0 0 0 .37 0 0 0 0 .79 0 0 0 0 1 0 0 0 .36 0"/>
      <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <polygon points="{outer}" fill="url(#glass)" opacity=".74" filter="url(#glow)"/>
  <polyline points="{outer}" fill="none" stroke="{COLORS["white"]}" stroke-width="5" opacity=".66" stroke-linejoin="round"/>
  <path d="M99 108 L180 62 L260 108" fill="none" stroke="{COLORS["white"]}" stroke-width="5" opacity=".42" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""",
    }

    result: dict[str, Path] = {}
    for name, content in templates.items():
        path = TEMPLATE_DIR / f"{name}.svg"
        path.write_text(content, encoding="utf-8")
        result[name] = path
    return result


def add_hex(
    items: list[dict],
    poster: dict,
    layer_group: str,
    template: str,
    lx: float,
    ly: float,
    radius: float,
    opacity: float,
    rotation: float,
    blend: str = "normal",
    blur: float = 0.0,
    name_prefix: str = "hex",
) -> None:
    x = poster["x"] + lx
    y = poster["y"] + ly
    items.append(
        {
            "poster": poster["idx"],
            "group": layer_group,
            "template": template,
            "name": f"{name_prefix}_{len(items) + 1:04d}",
            "x": round(x, 2),
            "y": round(y, 2),
            "r": round(radius, 2),
            "opacity": round(opacity, 2),
            "rotation": round(rotation, 2),
            "blend": blend,
            "blur": round(blur, 2),
        }
    )


def in_local(lx: float, ly: float, pad: float = 80) -> bool:
    return -pad <= lx <= POSTER_W + pad and -pad <= ly <= POSTER_H + pad


def generate_dense(poster: dict, rng: random.Random) -> tuple[list[dict], dict]:
    items: list[dict] = []
    # Dense energy cloud from upper-left to lower-right, leaving lower text area quiet.
    attempts = 0
    while len(items) < 158 and attempts < 4000:
        attempts += 1
        t = rng.betavariate(0.58, 2.8)
        lx = 160 + t * 1320 + rng.gauss(0, 72 + 190 * t)
        ly = 120 + t * 1380 + rng.gauss(0, 70 + 170 * t)
        if ly > 1810 and rng.random() > 0.12:
            continue
        if not in_local(lx, ly):
            continue
        close = 1 - t
        if close > 0.76 and rng.random() < 0.28:
            radius = rng.uniform(160, 310)
        elif close > 0.52:
            radius = rng.uniform(72, 170)
        elif close > 0.24:
            radius = rng.uniform(24, 82)
        else:
            radius = rng.uniform(7, 28)
        opacity = clamp(12 + 78 * close**1.55 + rng.gauss(0, 6), 8, 90)
        blur = 0 if radius > 42 else rng.uniform(0.3, 2.4)
        if radius <= 18:
            template = "Hex_Micro_Particle"
            group = "C_远景粒子六边形层"
            blend = "screen"
        elif rng.random() < 0.22:
            template = "Hex_Glass_Glow"
            group = "D_玻璃透明六边形层"
            blend = "screen"
            opacity *= 0.72
        elif rng.random() < 0.34:
            template = "Hex_Outline_Frame"
            group = "B_主六边形层"
            blend = "screen"
        elif rng.random() < 0.52:
            template = "Hex_TechBlue_Solid"
            group = "B_主六边形层"
            blend = "normal"
        else:
            template = "Hex_DeepBlue_Solid"
            group = "B_主六边形层"
            blend = "normal"
        add_hex(
            items,
            poster,
            group,
            template,
            lx,
            ly,
            radius,
            opacity,
            rng.uniform(-7, 7),
            blend,
            blur,
            "p1_hex",
        )

    effects = {
        "fog": [
            {
                "x": 210,
                "y": 170,
                "rx": 620,
                "ry": 430,
                "color": COLORS["ice"],
                "opacity": 18,
                "blur": 84,
                "blend": "screen",
            },
            {
                "x": 520,
                "y": 470,
                "rx": 560,
                "ry": 390,
                "color": COLORS["sky"],
                "opacity": 13,
                "blur": 98,
                "blend": "screen",
            },
            {
                "x": 870,
                "y": 850,
                "rx": 540,
                "ry": 430,
                "color": COLORS["ice"],
                "opacity": 10,
                "blur": 110,
                "blend": "softLight",
            },
        ],
        "bokeh": [],
        "data": [],
        "grid": False,
    }
    for _ in range(42):
        t = rng.betavariate(0.65, 3.1)
        effects["bokeh"].append(
            {
                "x": round(120 + t * 1180 + rng.gauss(0, 120 + 100 * t), 2),
                "y": round(90 + t * 1200 + rng.gauss(0, 120 + 90 * t), 2),
                "r": round(rng.uniform(9, 60) * (1.15 - t * 0.45), 2),
                "color": COLORS["ice"] if rng.random() < 0.72 else COLORS["sky"],
                "opacity": round(rng.uniform(8, 30) * (1 - t * 0.44), 2),
                "blur": round(rng.uniform(15, 45), 2),
            }
        )
    return items, effects


def generate_minimal(poster: dict, rng: random.Random) -> tuple[list[dict], dict]:
    items: list[dict] = []
    attempts = 0
    while len(items) < 34 and attempts < 1200:
        attempts += 1
        t = rng.betavariate(0.72, 3.0)
        lx = POSTER_W - 170 - t * 980 + rng.gauss(0, 72 + 125 * t)
        ly = 130 + t * 1000 + rng.gauss(0, 64 + 100 * t)
        if ly > 1530 or not in_local(lx, ly, 30):
            continue
        close = 1 - t
        radius = rng.uniform(28, 142) * (0.62 + close * 0.55)
        opacity = clamp(8 + 42 * close**1.7 + rng.gauss(0, 2.5), 6, 48)
        template = "Hex_Outline_Frame" if rng.random() < 0.58 else "Hex_Ice_Transparent"
        group = "B_主六边形层" if template == "Hex_Outline_Frame" else "D_玻璃透明六边形层"
        add_hex(
            items,
            poster,
            group,
            template,
            lx,
            ly,
            radius,
            opacity,
            rng.uniform(-5, 5),
            "screen",
            rng.uniform(0, 0.8),
            "p2_hex",
        )

    effects = {
        "fog": [
            {
                "x": 1450,
                "y": 230,
                "rx": 510,
                "ry": 360,
                "color": COLORS["ice"],
                "opacity": 6,
                "blur": 120,
                "blend": "softLight",
            },
        ],
        "bokeh": [],
        "data": [],
        "grid": False,
    }
    return items, effects


def generate_data(poster: dict, rng: random.Random) -> tuple[list[dict], dict]:
    items: list[dict] = []
    nodes: list[dict] = []
    attempts = 0
    while len(items) < 92 and attempts < 2400:
        attempts += 1
        t = rng.betavariate(0.67, 2.7)
        lx = POSTER_W - 250 - t * 860 + rng.gauss(0, 80 + 140 * t)
        ly = 120 + t * 1120 + rng.gauss(0, 74 + 120 * t)
        if ly > 1720 and rng.random() > 0.18:
            continue
        if not in_local(lx, ly):
            continue
        close = 1 - t
        radius = rng.choice([rng.uniform(68, 156), rng.uniform(20, 70), rng.uniform(8, 24)])
        if close > 0.68 and rng.random() < 0.24:
            radius = rng.uniform(120, 230)
        opacity = clamp(12 + 58 * close**1.45 + rng.gauss(0, 5), 10, 76)
        if radius < 18:
            template = "Hex_Micro_Particle"
            group = "C_远景粒子六边形层"
            blend = "screen"
        elif rng.random() < 0.34:
            template = "Hex_Outline_Frame"
            group = "B_主六边形层"
            blend = "screen"
        elif rng.random() < 0.25:
            template = "Hex_Ice_Transparent"
            group = "D_玻璃透明六边形层"
            blend = "screen"
        else:
            template = "Hex_TechBlue_Solid" if rng.random() < 0.64 else "Hex_DeepBlue_Solid"
            group = "B_主六边形层"
            blend = "normal"
        add_hex(
            items,
            poster,
            group,
            template,
            lx,
            ly,
            radius,
            opacity,
            rng.uniform(-6, 6),
            blend,
            rng.uniform(0, 1.6 if radius < 26 else 0.4),
            "p3_hex",
        )
        if radius > 32 and ly < 1180:
            nodes.append({"x": lx, "y": ly, "r": radius})

    data_lines: list[dict] = []
    sorted_nodes = sorted(nodes, key=lambda n: n["r"], reverse=True)[:28]
    for i, a in enumerate(sorted_nodes):
        candidates = []
        for j, b in enumerate(sorted_nodes):
            if i == j:
                continue
            d = math.dist((a["x"], a["y"]), (b["x"], b["y"]))
            if 80 < d < 360:
                candidates.append((d, b))
        candidates.sort(key=lambda x: x[0])
        for _, b in candidates[:2]:
            if rng.random() < 0.58:
                data_lines.append(
                    {
                        "type": "line",
                        "x1": round(a["x"], 2),
                        "y1": round(a["y"], 2),
                        "x2": round(b["x"], 2),
                        "y2": round(b["y"], 2),
                        "w": round(rng.uniform(1.0, 2.4), 2),
                        "color": COLORS["sky"] if rng.random() < 0.62 else COLORS["tech"],
                        "opacity": round(rng.uniform(16, 38), 2),
                        "dash": rng.random() < 0.35,
                    }
                )

    for _ in range(28):
        x = rng.uniform(920, 1660)
        y1 = rng.uniform(360, 980)
        length = rng.uniform(260, 950)
        data_lines.append(
            {
                "type": "fall",
                "x1": round(x, 2),
                "y1": round(y1, 2),
                "x2": round(x + rng.uniform(-12, 12), 2),
                "y2": round(min(1850, y1 + length), 2),
                "w": round(rng.uniform(1.0, 2.0), 2),
                "color": COLORS["sky"],
                "opacity": round(rng.uniform(10, 30), 2),
                "dash": True,
            }
        )

    for _ in range(80):
        y = rng.uniform(390, 1810)
        fade = 1 - clamp((y - 390) / 1420, 0, 1)
        data_lines.append(
            {
                "type": "node",
                "x": round(rng.uniform(850, 1700) + rng.gauss(0, 30), 2),
                "y": round(y, 2),
                "r": round(rng.uniform(1.8, 5.8), 2),
                "color": COLORS["sky"] if rng.random() < 0.75 else COLORS["tech"],
                "opacity": round(rng.uniform(8, 28) * (0.38 + fade * 0.8), 2),
            }
        )

    effects = {
        "fog": [
            {
                "x": 1460,
                "y": 300,
                "rx": 560,
                "ry": 390,
                "color": COLORS["ice"],
                "opacity": 11,
                "blur": 100,
                "blend": "screen",
            },
            {
                "x": 1290,
                "y": 850,
                "rx": 410,
                "ry": 720,
                "color": COLORS["sky"],
                "opacity": 6,
                "blur": 130,
                "blend": "softLight",
            },
        ],
        "bokeh": [
            {"x": 1530, "y": 260, "r": 44, "color": COLORS["ice"], "opacity": 8, "blur": 32},
            {"x": 1180, "y": 760, "r": 26, "color": COLORS["sky"], "opacity": 6, "blur": 30},
            {"x": 1600, "y": 960, "r": 18, "color": COLORS["ice"], "opacity": 5, "blur": 24},
        ],
        "data": data_lines,
        "grid": True,
    }
    return items, effects


def generate_diagonal(poster: dict, rng: random.Random) -> tuple[list[dict], dict]:
    items: list[dict] = []
    attempts = 0
    while len(items) < 108 and attempts < 2400:
        attempts += 1
        t = rng.random()
        lx = 170 + t * 1460 + rng.gauss(0, 100 + 70 * math.sin(t * math.pi))
        ly = 120 + t * 1540 + rng.gauss(0, 88 + 80 * math.sin(t * math.pi))
        if ly > 1890 and rng.random() > 0.16:
            continue
        if not in_local(lx, ly):
            continue
        edge_density = 0.65 + 0.35 * math.cos((t - 0.18) * math.pi)
        if rng.random() < 0.18:
            radius = rng.uniform(120, 260) * edge_density
        elif rng.random() < 0.58:
            radius = rng.uniform(44, 132) * edge_density
        else:
            radius = rng.uniform(8, 42)
        opacity = clamp(
            12 + 56 * (0.72 + 0.28 * math.cos((t - 0.18) * math.pi)) + rng.gauss(0, 8), 8, 78
        )
        if radius < 16:
            template = "Hex_Micro_Particle"
            group = "C_远景粒子六边形层"
            blend = "screen"
        elif rng.random() < 0.36:
            template = "Hex_Outline_Frame"
            group = "B_主六边形层"
            blend = "screen"
        elif rng.random() < 0.25:
            template = "Hex_Ice_Transparent"
            group = "D_玻璃透明六边形层"
            blend = "screen"
            opacity *= 0.75
        elif rng.random() < 0.18:
            template = "Hex_Glass_Glow"
            group = "D_玻璃透明六边形层"
            blend = "screen"
            opacity *= 0.62
        else:
            template = "Hex_TechBlue_Solid" if rng.random() < 0.6 else "Hex_DeepBlue_Solid"
            group = "B_主六边形层"
            blend = "normal"
        add_hex(
            items,
            poster,
            group,
            template,
            lx,
            ly,
            radius,
            opacity,
            rng.uniform(-7, 7),
            blend,
            rng.uniform(0, 1.7 if radius < 24 else 0.45),
            "p4_hex",
        )

    effects = {
        "fog": [
            {
                "x": 420,
                "y": 360,
                "rx": 480,
                "ry": 330,
                "color": COLORS["ice"],
                "opacity": 9,
                "blur": 90,
                "blend": "screen",
            },
            {
                "x": 1280,
                "y": 1270,
                "rx": 520,
                "ry": 430,
                "color": COLORS["sky"],
                "opacity": 8,
                "blur": 115,
                "blend": "softLight",
            },
        ],
        "bokeh": [],
        "data": [],
        "grid": True,
    }
    for _ in range(18):
        t = rng.random()
        effects["bokeh"].append(
            {
                "x": round(200 + t * 1450 + rng.gauss(0, 120), 2),
                "y": round(150 + t * 1430 + rng.gauss(0, 110), 2),
                "r": round(rng.uniform(10, 48), 2),
                "color": COLORS["ice"] if rng.random() < 0.72 else COLORS["sky"],
                "opacity": round(rng.uniform(7, 20), 2),
                "blur": round(rng.uniform(18, 42), 2),
            }
        )
    for _ in range(34):
        t = rng.random()
        effects["data"].append(
            {
                "type": "node",
                "x": round(200 + t * 1450 + rng.gauss(0, 90), 2),
                "y": round(160 + t * 1500 + rng.gauss(0, 90), 2),
                "r": round(rng.uniform(1.7, 4.3), 2),
                "color": COLORS["sky"],
                "opacity": round(rng.uniform(8, 22), 2),
            }
        )
    return items, effects


def generate_layout() -> dict:
    rng = random.Random(SEED)
    all_items: list[dict] = []
    effects: dict[str, dict] = {}
    generators = {
        "dense_glow": generate_dense,
        "minimal_white": generate_minimal,
        "data_flow": generate_data,
        "diagonal_scatter": generate_diagonal,
    }
    for poster in POSTERS:
        items, fx = generators[poster["kind"]](poster, rng)
        all_items.extend(items)
        effects[str(poster["idx"])] = fx
    return {
        "posters": POSTERS,
        "hexItems": all_items,
        "effects": effects,
    }


def build_jsx(template_paths: dict[str, Path], layout: dict) -> str:
    data = {
        "doc": {
            "name": DOC_NAME,
            "width": WIDTH,
            "height": HEIGHT,
            "dpi": DPI,
            "posterW": POSTER_W,
            "posterH": POSTER_H,
            "safe": SAFE,
            "root": js_path(ROOT),
            "work": js_path(WORK),
            "psd": js_path(ROOT / PSD_NAME),
            "whitePng": js_path(ROOT / WHITE_PNG_NAME),
            "transparentPng": js_path(ROOT / TRANSPARENT_PNG_NAME),
            "jpg": js_path(ROOT / JPG_NAME),
            "log": js_path(WORK / "photoshop_automation_log.txt"),
        },
        "colors": COLORS,
        "templates": {name: js_path(path) for name, path in template_paths.items()},
        **layout,
    }
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return f"""#target photoshop
app.displayDialogs = DialogModes.NO;
app.preferences.rulerUnits = Units.PIXELS;

var DATA = {payload};

var doc = null;
var templateLayers = {{}};
var posterGroups = {{}};
var posterSubGroups = {{}};
var backgroundLayer = null;
var transparentHideLayers = [];

function log(msg) {{
    try {{
        var f = new File(DATA.doc.log);
        f.encoding = "UTF-8";
        f.open("a");
        f.writeln(new Date().toISOString ? new Date().toISOString() + " " + msg : msg);
        f.close();
    }} catch (e) {{}}
}}

function solid(hex) {{
    var c = new SolidColor();
    var v = hex.replace("#", "");
    c.rgb.red = parseInt(v.substring(0, 2), 16);
    c.rgb.green = parseInt(v.substring(2, 4), 16);
    c.rgb.blue = parseInt(v.substring(4, 6), 16);
    return c;
}}

function rgbDesc(hex) {{
    var v = hex.replace("#", "");
    var d = new ActionDescriptor();
    d.putDouble(charIDToTypeID("Rd  "), parseInt(v.substring(0, 2), 16));
    d.putDouble(charIDToTypeID("Grn "), parseInt(v.substring(2, 4), 16));
    d.putDouble(charIDToTypeID("Bl  "), parseInt(v.substring(4, 6), 16));
    return d;
}}

function setBlend(layer, blendName) {{
    try {{
        if (blendName == "screen") layer.blendMode = BlendMode.SCREEN;
        else if (blendName == "multiply") layer.blendMode = BlendMode.MULTIPLY;
        else if (blendName == "softLight") layer.blendMode = BlendMode.SOFTLIGHT;
        else if (blendName == "overlay") layer.blendMode = BlendMode.OVERLAY;
        else layer.blendMode = BlendMode.NORMAL;
    }} catch (e) {{}}
}}

function layerBounds(layer) {{
    var b = layer.bounds;
    return [b[0].as("px"), b[1].as("px"), b[2].as("px"), b[3].as("px")];
}}

function centerLayer(layer, x, y) {{
    var b = layerBounds(layer);
    var cx = (b[0] + b[2]) / 2;
    var cy = (b[1] + b[3]) / 2;
    layer.translate(x - cx, y - cy);
}}

function deleteIfExists(path) {{
    try {{
        var f = new File(path);
        if (f.exists) f.remove();
    }} catch (e) {{
        log("Could not remove existing file: " + path + " / " + e);
    }}
}}

function placeFile(path) {{
    var desc = new ActionDescriptor();
    desc.putPath(charIDToTypeID("null"), new File(path));
    desc.putEnumerated(charIDToTypeID("FTcs"), charIDToTypeID("QCSt"), charIDToTypeID("Qcsa"));
    var offset = new ActionDescriptor();
    offset.putUnitDouble(charIDToTypeID("Hrzn"), charIDToTypeID("#Pxl"), 0);
    offset.putUnitDouble(charIDToTypeID("Vrtc"), charIDToTypeID("#Pxl"), 0);
    desc.putObject(charIDToTypeID("Ofst"), charIDToTypeID("Ofst"), offset);
    executeAction(charIDToTypeID("Plc "), desc, DialogModes.NO);
    return app.activeDocument.activeLayer;
}}

function applyOuterGlow(layer, hex, opacity, size) {{
    try {{
        doc.activeLayer = layer;
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("Lefx"));
        ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        desc.putReference(charIDToTypeID("null"), ref);
        var fx = new ActionDescriptor();
        fx.putUnitDouble(charIDToTypeID("Scl "), charIDToTypeID("#Prc"), 100);
        var glow = new ActionDescriptor();
        glow.putBoolean(charIDToTypeID("enab"), true);
        glow.putEnumerated(charIDToTypeID("Md  "), charIDToTypeID("BlnM"), charIDToTypeID("Scrn"));
        glow.putUnitDouble(charIDToTypeID("Opct"), charIDToTypeID("#Prc"), opacity);
        glow.putObject(charIDToTypeID("Clr "), charIDToTypeID("RGBC"), rgbDesc(hex));
        glow.putUnitDouble(charIDToTypeID("Ckmt"), charIDToTypeID("#Pxl"), 0);
        glow.putUnitDouble(charIDToTypeID("blur"), charIDToTypeID("#Pxl"), size);
        glow.putUnitDouble(charIDToTypeID("Nose"), charIDToTypeID("#Prc"), 0);
        fx.putObject(charIDToTypeID("OrGl"), charIDToTypeID("OrGl"), glow);
        desc.putObject(charIDToTypeID("T   "), charIDToTypeID("Lefx"), fx);
        executeAction(charIDToTypeID("setd"), desc, DialogModes.NO);
    }} catch (e) {{
        log("Outer glow skipped on " + layer.name + ": " + e);
    }}
}}

function applyDropShadow(layer, hex, opacity, distance, size) {{
    try {{
        doc.activeLayer = layer;
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("Lefx"));
        ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        desc.putReference(charIDToTypeID("null"), ref);
        var fx = new ActionDescriptor();
        fx.putUnitDouble(charIDToTypeID("Scl "), charIDToTypeID("#Prc"), 100);
        var shadow = new ActionDescriptor();
        shadow.putBoolean(charIDToTypeID("enab"), true);
        shadow.putEnumerated(charIDToTypeID("Md  "), charIDToTypeID("BlnM"), charIDToTypeID("Mltp"));
        shadow.putObject(charIDToTypeID("Clr "), charIDToTypeID("RGBC"), rgbDesc(hex));
        shadow.putUnitDouble(charIDToTypeID("Opct"), charIDToTypeID("#Prc"), opacity);
        shadow.putUnitDouble(charIDToTypeID("lagl"), charIDToTypeID("#Ang"), 90);
        shadow.putUnitDouble(charIDToTypeID("Dstn"), charIDToTypeID("#Pxl"), distance);
        shadow.putUnitDouble(charIDToTypeID("Ckmt"), charIDToTypeID("#Prc"), 0);
        shadow.putUnitDouble(charIDToTypeID("blur"), charIDToTypeID("#Pxl"), size);
        fx.putObject(charIDToTypeID("DrSh"), charIDToTypeID("DrSh"), shadow);
        desc.putObject(charIDToTypeID("T   "), charIDToTypeID("Lefx"), fx);
        executeAction(charIDToTypeID("setd"), desc, DialogModes.NO);
    }} catch (e) {{
        log("Drop shadow skipped on " + layer.name + ": " + e);
    }}
}}

function addMaskFromSelection(layer) {{
    try {{
        doc.activeLayer = layer;
        var desc = new ActionDescriptor();
        desc.putClass(charIDToTypeID("Nw  "), charIDToTypeID("Chnl"));
        var ref = new ActionReference();
        ref.putEnumerated(charIDToTypeID("Chnl"), charIDToTypeID("Chnl"), charIDToTypeID("Msk "));
        desc.putReference(charIDToTypeID("At  "), ref);
        desc.putEnumerated(charIDToTypeID("Usng"), charIDToTypeID("UsrM"), charIDToTypeID("RvlS"));
        executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO);
        doc.selection.deselect();
    }} catch (e) {{
        log("Layer mask skipped on " + layer.name + ": " + e);
        try {{ doc.selection.deselect(); }} catch (ee) {{}}
    }}
}}

function selectRect(x, y, w, h, feather) {{
    doc.selection.select([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], SelectionType.REPLACE, feather || 0, true);
}}

function selectPoly(points, feather) {{
    doc.selection.select(points, SelectionType.REPLACE, feather || 0, true);
}}

function fillPoly(layer, points, colorHex, opacity, feather) {{
    doc.activeLayer = layer;
    selectPoly(points, feather || 0);
    doc.selection.fill(solid(colorHex), ColorBlendMode.NORMAL, Math.max(1, Math.min(100, Math.round(opacity))), false);
    doc.selection.deselect();
}}

function ellipsePoints(cx, cy, rx, ry, n) {{
    var pts = [];
    for (var i = 0; i < n; i++) {{
        var a = Math.PI * 2 * i / n;
        pts.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]);
    }}
    return pts;
}}

function lineRect(x1, y1, x2, y2, width) {{
    var dx = x2 - x1;
    var dy = y2 - y1;
    var len = Math.sqrt(dx * dx + dy * dy);
    if (len < 0.001) len = 1;
    var px = -dy / len * width / 2;
    var py = dx / len * width / 2;
    return [[x1 + px, y1 + py], [x2 + px, y2 + py], [x2 - px, y2 - py], [x1 - px, y1 - py]];
}}

function drawLine(layer, x1, y1, x2, y2, width, colorHex, opacity, dashed) {{
    if (!dashed) {{
        fillPoly(layer, lineRect(x1, y1, x2, y2, width), colorHex, opacity, 0);
        return;
    }}
    var dx = x2 - x1;
    var dy = y2 - y1;
    var len = Math.sqrt(dx * dx + dy * dy);
    var dash = 24;
    var gap = 20;
    var pos = 0;
    while (pos < len) {{
        var end = Math.min(len, pos + dash);
        var t1 = pos / len;
        var t2 = end / len;
        fillPoly(layer, lineRect(x1 + dx * t1, y1 + dy * t1, x1 + dx * t2, y1 + dy * t2, width), colorHex, opacity, 0);
        pos += dash + gap;
    }}
}}

function makeRasterLayer(parent, name, blend, opacity) {{
    var layer = doc.artLayers.add();
    layer.name = name;
    setBlend(layer, blend || "normal");
    layer.opacity = opacity == null ? 100 : opacity;
    layer.move(parent, ElementPlacement.PLACEATBEGINNING);
    return layer;
}}

function makeGroup(parent, name) {{
    var g = parent.layerSets.add();
    g.name = name;
    return g;
}}

function makeAdjustmentLayer(parent, typeChar, name, opacity, blend) {{
    try {{
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putClass(charIDToTypeID("AdjL"));
        desc.putReference(charIDToTypeID("null"), ref);
        var adj = new ActionDescriptor();
        var typeDesc = new ActionDescriptor();
        adj.putObject(charIDToTypeID("Type"), charIDToTypeID(typeChar), typeDesc);
        desc.putObject(charIDToTypeID("Usng"), charIDToTypeID("AdjL"), adj);
        executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO);
        var layer = doc.activeLayer;
        layer.name = name;
        layer.opacity = opacity;
        setBlend(layer, blend || "normal");
        layer.move(parent, ElementPlacement.PLACEATBEGINNING);
        return layer;
    }} catch (e) {{
        log("Adjustment layer skipped " + name + ": " + e);
        return makeRasterLayer(parent, name + "_替代柔光层", blend || "softLight", opacity);
    }}
}}

function makeGradientMap(parent, name, opacity) {{
    try {{
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putClass(charIDToTypeID("AdjL"));
        desc.putReference(charIDToTypeID("null"), ref);

        var adj = new ActionDescriptor();
        var typeDesc = new ActionDescriptor();
        var grad = new ActionDescriptor();
        grad.putString(charIDToTypeID("Nm  "), "Cold Blue To White");
        grad.putEnumerated(charIDToTypeID("GrdF"), charIDToTypeID("GrdF"), charIDToTypeID("CstS"));
        grad.putDouble(charIDToTypeID("Intr"), 4096);

        var stops = new ActionList();
        var colors = [
            [0, DATA.colors.deep],
            [1024, DATA.colors.tech],
            [2100, DATA.colors.sky],
            [3200, DATA.colors.ice],
            [4096, DATA.colors.white]
        ];
        for (var i = 0; i < colors.length; i++) {{
            var s = new ActionDescriptor();
            s.putObject(charIDToTypeID("Clr "), charIDToTypeID("RGBC"), rgbDesc(colors[i][1]));
            s.putEnumerated(charIDToTypeID("Type"), charIDToTypeID("Clry"), charIDToTypeID("UsrS"));
            s.putInteger(charIDToTypeID("Lctn"), colors[i][0]);
            s.putInteger(charIDToTypeID("Mdpn"), 50);
            stops.putObject(charIDToTypeID("Clrt"), s);
        }}
        grad.putList(charIDToTypeID("Clrs"), stops);

        var trans = new ActionList();
        var t1 = new ActionDescriptor();
        t1.putUnitDouble(charIDToTypeID("Opct"), charIDToTypeID("#Prc"), 100);
        t1.putInteger(charIDToTypeID("Lctn"), 0);
        t1.putInteger(charIDToTypeID("Mdpn"), 50);
        trans.putObject(charIDToTypeID("TrnS"), t1);
        var t2 = new ActionDescriptor();
        t2.putUnitDouble(charIDToTypeID("Opct"), charIDToTypeID("#Prc"), 100);
        t2.putInteger(charIDToTypeID("Lctn"), 4096);
        t2.putInteger(charIDToTypeID("Mdpn"), 50);
        trans.putObject(charIDToTypeID("TrnS"), t2);
        grad.putList(charIDToTypeID("Trns"), trans);

        typeDesc.putObject(charIDToTypeID("Grad"), charIDToTypeID("Grdn"), grad);
        adj.putObject(charIDToTypeID("Type"), charIDToTypeID("GdMp"), typeDesc);
        desc.putObject(charIDToTypeID("Usng"), charIDToTypeID("AdjL"), adj);
        executeAction(charIDToTypeID("Mk  "), desc, DialogModes.NO);
        var layer = doc.activeLayer;
        layer.name = name;
        layer.opacity = opacity;
        setBlend(layer, "softLight");
        layer.move(parent, ElementPlacement.PLACEATBEGINNING);
        return layer;
    }} catch (e) {{
        log("Gradient map skipped " + name + ": " + e);
        var layer2 = makeRasterLayer(parent, name + "_替代冷蓝柔光", "softLight", opacity);
        return layer2;
    }}
}}

function addNoiseLayer(parent, name, x, y, w, h, opacity) {{
    var layer = makeRasterLayer(parent, name, "softLight", opacity);
    doc.activeLayer = layer;
    selectRect(x, y, w, h, 0);
    doc.selection.fill(solid(DATA.colors.white), ColorBlendMode.NORMAL, 100, false);
    doc.selection.deselect();
    try {{
        layer.applyAddNoise(1.0, NoiseDistribution.UNIFORM, true);
    }} catch (e) {{
        log("Noise filter skipped: " + e);
    }}
    transparentHideLayers.push(layer);
    return layer;
}}

function addGuides() {{
    for (var i = 0; i < DATA.posters.length; i++) {{
        var p = DATA.posters[i];
        var x = p.x, y = p.y, w = DATA.doc.posterW, h = DATA.doc.posterH, s = DATA.doc.safe;
        doc.guides.add(Direction.VERTICAL, UnitValue(x, "px"));
        doc.guides.add(Direction.VERTICAL, UnitValue(x + w, "px"));
        doc.guides.add(Direction.HORIZONTAL, UnitValue(y, "px"));
        doc.guides.add(Direction.HORIZONTAL, UnitValue(y + h, "px"));
        doc.guides.add(Direction.VERTICAL, UnitValue(x + s, "px"));
        doc.guides.add(Direction.VERTICAL, UnitValue(x + w - s, "px"));
        doc.guides.add(Direction.HORIZONTAL, UnitValue(y + s, "px"));
        doc.guides.add(Direction.HORIZONTAL, UnitValue(y + h - s, "px"));
        doc.guides.add(Direction.HORIZONTAL, UnitValue(y + h - 680, "px"));
        doc.guides.add(Direction.HORIZONTAL, UnitValue(y + h - 440, "px"));
    }}
}}

function createTemplates(library) {{
    for (var name in DATA.templates) {{
        if (!DATA.templates.hasOwnProperty(name)) continue;
        var layer = placeFile(DATA.templates[name]);
        layer.name = name;
        layer.opacity = 100;
        centerLayer(layer, 90, 90);
        layer.move(library, ElementPlacement.PLACEATBEGINNING);
        applyOuterGlow(layer, DATA.colors.sky, name == "Hex_DeepBlue_Solid" ? 35 : 18, name == "Hex_DeepBlue_Solid" ? 40 : 18);
        templateLayers[name] = layer;
    }}
    library.name = "00_六边形智能对象模板库";
    library.visible = false;
}}

function placeHex(item) {{
    var tmpl = templateLayers[item.template];
    if (!tmpl) {{
        log("Missing template " + item.template);
        return;
    }}
    var parent = posterSubGroups[item.poster][item.group];
    var layer = tmpl.duplicate(parent, ElementPlacement.PLACEATBEGINNING);
    layer.name = item.name + "_" + item.template;
    layer.visible = true;
    layer.opacity = item.opacity;
    setBlend(layer, item.blend);
    doc.activeLayer = layer;
    try {{
        var scale = item.r / 150.0 * 100.0;
        layer.resize(scale, scale, AnchorPosition.MIDDLECENTER);
        if (Math.abs(item.rotation) > 0.01) layer.rotate(item.rotation, AnchorPosition.MIDDLECENTER);
        centerLayer(layer, item.x, item.y);
        if (item.blur && item.blur > 0.15) layer.applyGaussianBlur(item.blur);
    }} catch (e) {{
        log("Transform skipped on " + layer.name + ": " + e);
    }}
}}

function createPosterStructure() {{
    var rootNames = [
        "A_底色层",
        "B_主六边形层",
        "C_远景粒子六边形层",
        "D_玻璃透明六边形层",
        "E_光效辉光层",
        "F_Bokeh散景层",
        "G_数据线条层",
        "H_渐变蒙版层",
        "I_卡片投影层",
        "J_全局调色层",
        "K_质感收尾层"
    ];
    for (var i = 0; i < DATA.posters.length; i++) {{
        var p = DATA.posters[i];
        var g = doc.layerSets.add();
        g.name = p.name;
        posterGroups[p.idx] = g;
        posterSubGroups[p.idx] = {{}};
        for (var j = 0; j < rootNames.length; j++) {{
            var sub = g.layerSets.add();
            sub.name = rootNames[j];
            posterSubGroups[p.idx][rootNames[j]] = sub;
        }}
    }}
}}

function addPosterBaseAndShadow() {{
    for (var i = 0; i < DATA.posters.length; i++) {{
        var p = DATA.posters[i];
        var x = p.x, y = p.y, w = DATA.doc.posterW, h = DATA.doc.posterH;
        var baseGroup = posterSubGroups[p.idx]["A_底色层"];
        var base = makeRasterLayer(baseGroup, "A_纯白底色_锁定", "normal", 100);
        selectRect(x, y, w, h, 0);
        doc.selection.fill(solid(DATA.colors.white), ColorBlendMode.NORMAL, 100, false);
        doc.selection.deselect();
        try {{ base.allLocked = true; }} catch (e) {{}}
        transparentHideLayers.push(base);

        var tint = makeRasterLayer(baseGroup, "A_极淡冷蓝呼吸底色", "softLight", p.idx == 2 ? 28 : 38);
        fillPoly(tint, ellipsePoints(x + w * 0.70, y + h * 0.26, w * 0.54, h * 0.35, 42), DATA.colors.pale, 34, 0);
        try {{ tint.applyGaussianBlur(95); }} catch (e2) {{}}
        transparentHideLayers.push(tint);

        var shGroup = posterSubGroups[p.idx]["I_卡片投影层"];
        var shadow = makeRasterLayer(shGroup, "I_卡片底部悬浮投影", "multiply", 12);
        fillPoly(shadow, ellipsePoints(x + w / 2, y + h + 30, w * 0.44, 42, 44), DATA.colors.deep, 80, 0);
        try {{ shadow.applyGaussianBlur(92); }} catch (e3) {{}}
        applyDropShadow(base, DATA.colors.deep, 10, 26, 95);
    }}
}}

function addEffects() {{
    for (var i = 0; i < DATA.posters.length; i++) {{
        var p = DATA.posters[i];
        var fx = DATA.effects[p.idx.toString()];
        var x = p.x, y = p.y;
        var eg = posterSubGroups[p.idx]["E_光效辉光层"];
        for (var f = 0; f < fx.fog.length; f++) {{
            var fog = fx.fog[f];
            var layer = makeRasterLayer(eg, "E_空气透光光雾_" + (f + 1), fog.blend, fog.opacity);
            fillPoly(layer, ellipsePoints(x + fog.x, y + fog.y, fog.rx, fog.ry, 50), fog.color, 100, 0);
            try {{ layer.applyGaussianBlur(fog.blur); }} catch (e) {{}}
        }}

        var bg = posterSubGroups[p.idx]["F_Bokeh散景层"];
        for (var b = 0; b < fx.bokeh.length; b++) {{
            var bo = fx.bokeh[b];
            var bl = makeRasterLayer(bg, "F_Bokeh柔焦光斑_" + (b + 1), "screen", bo.opacity);
            fillPoly(bl, ellipsePoints(x + bo.x, y + bo.y, bo.r, bo.r, 32), bo.color, 100, 0);
            try {{ bl.applyGaussianBlur(bo.blur); }} catch (e4) {{}}
        }}

        var gg = posterSubGroups[p.idx]["G_数据线条层"];
        if (fx.grid) {{
            var grid = makeRasterLayer(gg, "G_极淡科技网格_1px", "screen", p.idx == 3 ? 7 : 5);
            for (var gx = x + 80; gx <= x + DATA.doc.posterW - 80; gx += 120) {{
                drawLine(grid, gx, y + 80, gx, y + DATA.doc.posterH - 760, 1, DATA.colors.sky, 45, false);
            }}
            for (var gy = y + 80; gy <= y + DATA.doc.posterH - 760; gy += 120) {{
                drawLine(grid, x + 80, gy, x + DATA.doc.posterW - 80, gy, 1, DATA.colors.sky, 45, false);
            }}
        }}
        if (fx.data && fx.data.length) {{
            var lines = makeRasterLayer(gg, p.idx == 3 ? "G_数据链路线条_节点_下坠粒子" : "G_对角细节点辅助", "screen", 100);
            for (var d = 0; d < fx.data.length; d++) {{
                var item = fx.data[d];
                if (item.type == "line" || item.type == "fall") {{
                    drawLine(lines, x + item.x1, y + item.y1, x + item.x2, y + item.y2, item.w, item.color, item.opacity, item.dash);
                }} else if (item.type == "node") {{
                    fillPoly(lines, ellipsePoints(x + item.x, y + item.y, item.r, item.r, 18), item.color, item.opacity, 0);
                }}
            }}
            try {{ lines.applyGaussianBlur(0.25); }} catch (e5) {{}}
        }}

        var hg = posterSubGroups[p.idx]["H_渐变蒙版层"];
        var fade = makeRasterLayer(hg, "H_白色渐变消散蒙版视觉层", "normal", p.idx == 2 ? 38 : 26);
        if (p.idx == 1) {{
            fillPoly(fade, ellipsePoints(x + 1660, y + 1880, 760, 650, 50), DATA.colors.white, 100, 0);
        }} else if (p.idx == 2) {{
            fillPoly(fade, ellipsePoints(x + 460, y + 1540, 920, 760, 50), DATA.colors.white, 100, 0);
        }} else if (p.idx == 3) {{
            fillPoly(fade, ellipsePoints(x + 760, y + 1950, 980, 680, 50), DATA.colors.white, 100, 0);
        }} else {{
            fillPoly(fade, ellipsePoints(x + 420, y + 2100, 920, 640, 50), DATA.colors.white, 100, 0);
        }}
        try {{ fade.applyGaussianBlur(135); }} catch (e6) {{}}
        transparentHideLayers.push(fade);
    }}
}}

function addAdjustmentAndTextureLayers() {{
    for (var i = 0; i < DATA.posters.length; i++) {{
        var p = DATA.posters[i];
        var jg = posterSubGroups[p.idx]["J_全局调色层"];
        makeGradientMap(jg, "J_渐变映射_冷蓝统一", p.idx == 2 ? 10 : 16);
        makeAdjustmentLayer(jg, "ClrB", "J_色彩平衡_冷蓝校准", 12, "normal");
        makeAdjustmentLayer(jg, "Crvs", "J_曲线_通透层次", 14, "normal");

        var kg = posterSubGroups[p.idx]["K_质感收尾层"];
        addNoiseLayer(kg, "K_单色极轻噪点_0_5到1_5", p.x, p.y, DATA.doc.posterW, DATA.doc.posterH, 6);
    }}

    var gg = doc.layerSets.add();
    gg.name = "99_全局统一校准";
    makeGradientMap(gg, "99_总体渐变映射_冷蓝到白", 12);
    makeAdjustmentLayer(gg, "Crvs", "99_总体曲线_高光通透", 10, "normal");
    makeAdjustmentLayer(gg, "ClrB", "99_总体色彩平衡_冷蓝", 10, "normal");
    makeAdjustmentLayer(gg, "Lvls", "99_总体色阶_清理灰雾", 8, "normal");
    addNoiseLayer(gg, "99_总体轻微噪点_0_5到1", 0, 0, DATA.doc.width, DATA.doc.height, 4);
}}

function addGroupMasks() {{
    for (var i = 0; i < DATA.posters.length; i++) {{
        var p = DATA.posters[i];
        selectRect(p.x - 58, p.y - 40, DATA.doc.posterW + 116, DATA.doc.posterH + 126, 0);
        addMaskFromSelection(posterGroups[p.idx]);
    }}
}}

function exportWhitePng() {{
    deleteIfExists(DATA.doc.whitePng);
    var opts = new PNGSaveOptions();
    doc.saveAs(new File(DATA.doc.whitePng), opts, true, Extension.LOWERCASE);
}}

function exportJpg() {{
    deleteIfExists(DATA.doc.jpg);
    var opts = new JPEGSaveOptions();
    opts.quality = 12;
    opts.embedColorProfile = true;
    opts.formatOptions = FormatOptions.STANDARDBASELINE;
    doc.saveAs(new File(DATA.doc.jpg), opts, true, Extension.LOWERCASE);
}}

function exportTransparentPng() {{
    var oldStates = [];
    for (var i = 0; i < transparentHideLayers.length; i++) {{
        oldStates.push([transparentHideLayers[i], transparentHideLayers[i].visible]);
        transparentHideLayers[i].visible = false;
    }}
    if (backgroundLayer) backgroundLayer.visible = false;
    deleteIfExists(DATA.doc.transparentPng);
    var opts = new PNGSaveOptions();
    doc.saveAs(new File(DATA.doc.transparentPng), opts, true, Extension.LOWERCASE);
    if (backgroundLayer) backgroundLayer.visible = true;
    for (var j = 0; j < oldStates.length; j++) oldStates[j][0].visible = oldStates[j][1];
}}

function addPreviewSmartObject() {{
    try {{
        var preview = placeFile(DATA.doc.whitePng);
        preview.name = "K_CameraRaw_最终质感预览";
        centerLayer(preview, DATA.doc.width / 2, DATA.doc.height / 2);
        preview.opacity = 100;
        setBlend(preview, "normal");
        try {{
            preview.applySmartSharpen(42, 0.5, 0, SmartSharpenType.LENSBLUR);
        }} catch (e) {{
            log("Smart sharpen preview skipped: " + e);
        }}
    }} catch (e2) {{
        log("Preview smart object skipped: " + e2);
    }}
}}

function savePsd() {{
    deleteIfExists(DATA.doc.psd);
    var opts = new PhotoshopSaveOptions();
    opts.layers = true;
    opts.embedColorProfile = true;
    doc.saveAs(new File(DATA.doc.psd), opts, false, Extension.LOWERCASE);
}}

function main() {{
    log("Starting 4-up hex poster automation");
    deleteIfExists(DATA.doc.log);
    doc = app.documents.add(
        UnitValue(DATA.doc.width, "px"),
        UnitValue(DATA.doc.height, "px"),
        DATA.doc.dpi,
        DATA.doc.name,
        NewDocumentMode.RGB,
        DocumentFill.TRANSPARENT,
        1,
        BitsPerChannelType.EIGHT,
        "sRGB IEC61966-2.1"
    );
    try {{ doc.convertProfile("sRGB IEC61966-2.1", Intent.RELATIVECOLORIMETRIC, true, true); }} catch (e) {{}}

    backgroundLayer = doc.artLayers.add();
    backgroundLayer.name = "00_整体纯白背景_#FFFFFF_锁定";
    selectRect(0, 0, DATA.doc.width, DATA.doc.height, 0);
    doc.selection.fill(solid(DATA.colors.white), ColorBlendMode.NORMAL, 100, false);
    doc.selection.deselect();
    backgroundLayer.move(doc, ElementPlacement.PLACEATEND);
    try {{ backgroundLayer.allLocked = true; }} catch (e0) {{}}

    addGuides();
    var library = doc.layerSets.add();
    createTemplates(library);
    createPosterStructure();
    addPosterBaseAndShadow();
    addEffects();
    for (var i = 0; i < DATA.hexItems.length; i++) {{
        placeHex(DATA.hexItems[i]);
        if (i % 50 == 0) log("Placed smart-object hex layers: " + i + "/" + DATA.hexItems.length);
    }}
    addAdjustmentAndTextureLayers();
    addGroupMasks();

    exportWhitePng();
    exportJpg();
    exportTransparentPng();
    addPreviewSmartObject();
    savePsd();
    log("Finished automation");
}}

try {{
    main();
}} catch (err) {{
    log("FATAL: " + err + " line=" + (err.line || "?"));
    throw err;
}}
"""


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    template_paths = write_template_svgs()
    layout = generate_layout()
    jsx = build_jsx(template_paths, layout)
    jsx_path = WORK / "generate_4up_hex_poster.jsx"
    jsx_path.write_text(jsx, encoding="utf-8-sig")
    manifest_path = WORK / "4up_hex_layout_manifest.json"
    manifest = {
        "doc": {
            "name": DOC_NAME,
            "width": WIDTH,
            "height": HEIGHT,
            "dpi": DPI,
            "colorMode": "RGB/8bit",
            "profile": "sRGB IEC61966-2.1",
        },
        "outputs": {
            "psd": str(ROOT / PSD_NAME),
            "whitePng": str(ROOT / WHITE_PNG_NAME),
            "transparentPng": str(ROOT / TRANSPARENT_PNG_NAME),
            "jpg": str(ROOT / JPG_NAME),
            "jsx": str(jsx_path),
        },
        "posterCount": len(POSTERS),
        "hexLayerCount": len(layout["hexItems"]),
        "posters": POSTERS,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

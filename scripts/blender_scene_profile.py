"""Profile .blend files for drawing and rendering study.

Run with Blender, for example:
blender --background --python scripts/blender_scene_profile.py -- --root <local-asset-root> --out docs\\blender-drawing-learning\\data\\blend_scene_profiles_redacted.json

The output is redacted for public repositories: it stores relative labels and
scene structure, not local absolute paths or source assets.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import bpy


def count_nodes(material) -> dict[str, int]:
    if not material or not material.use_nodes or not material.node_tree:
        return {}
    return dict(Counter(node.bl_idname for node in material.node_tree.nodes))


def material_profile(material) -> dict[str, object]:
    return {
        "name": material.name,
        "uses_nodes": bool(material.use_nodes),
        "node_types": count_nodes(material),
        "blend_method": getattr(material, "blend_method", None),
        "use_screen_refraction": bool(getattr(material, "use_screen_refraction", False)),
    }


def light_profile(light_obj) -> dict[str, object]:
    data = light_obj.data
    return {
        "name": light_obj.name,
        "type": data.type,
        "energy": round(float(getattr(data, "energy", 0.0)), 4),
        "color": [round(float(c), 4) for c in getattr(data, "color", [])],
    }


def camera_profile(camera_obj) -> dict[str, object]:
    data = camera_obj.data
    return {
        "name": camera_obj.name,
        "lens": round(float(getattr(data, "lens", 0.0)), 4),
        "sensor_width": round(float(getattr(data, "sensor_width", 0.0)), 4),
        "type": getattr(data, "type", None),
    }


def profile_blend(path: Path, root: Path) -> dict[str, object]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene = bpy.context.scene
    objects = list(bpy.data.objects)
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    lights = [obj for obj in objects if obj.type == "LIGHT"]
    cameras = [obj for obj in objects if obj.type == "CAMERA"]
    materials = list(bpy.data.materials)

    object_type_counts = Counter(obj.type for obj in objects)
    mesh_material_slot_counts = Counter(len(obj.material_slots) for obj in mesh_objects)
    modifier_counts = Counter()
    for obj in mesh_objects:
        for modifier in obj.modifiers:
            modifier_counts[modifier.type] += 1

    world = scene.world
    world_profile = {
        "has_world": bool(world),
        "uses_nodes": bool(world and world.use_nodes),
    }
    if world and not world.use_nodes:
        world_profile["color"] = [round(float(c), 4) for c in world.color]

    return {
        "relative_label": path.relative_to(root).as_posix(),
        "scene_name": scene.name,
        "render_engine": scene.render.engine,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "frame_range": [scene.frame_start, scene.frame_end],
        "object_count": len(objects),
        "object_type_counts": dict(object_type_counts),
        "mesh_count": len(mesh_objects),
        "material_count": len(materials),
        "light_count": len(lights),
        "camera_count": len(cameras),
        "mesh_material_slot_counts": dict(mesh_material_slot_counts),
        "modifier_counts": dict(modifier_counts),
        "lights": [light_profile(obj) for obj in lights[:12]],
        "cameras": [camera_profile(obj) for obj in cameras[:8]],
        "materials_sample": [material_profile(mat) for mat in materials[:20]],
        "world": world_profile,
        "drawing_learning_notes": infer_notes(scene.render.engine, lights, cameras, materials, modifier_counts),
    }


def infer_notes(render_engine, lights, cameras, materials, modifier_counts) -> list[str]:
    notes: list[str] = []
    if cameras:
        notes.append("Camera exists: study focal length and framing before rebuilding the scene.")
    if lights:
        notes.append("Lights exist: study key/fill/rim balance and light color before changing materials.")
    if any(mat.use_nodes for mat in materials):
        notes.append("Node materials exist: inspect shader graphs for color, roughness, normal, emission, and transparency decisions.")
    if "SUBSURF" in modifier_counts:
        notes.append("Subdivision modifiers exist: compare base mesh simplicity with final smoothed silhouette.")
    if "BEVEL" in modifier_counts:
        notes.append("Bevel modifiers exist: edges are likely softened for product-style highlights.")
    if render_engine:
        notes.append(f"Render engine is {render_engine}: keep lighting and material expectations aligned with that engine.")
    return notes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--match-label",
        default="",
        help="Only profile .blend files whose redacted relative label contains this text.",
    )
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    blend_files = sorted(root.rglob("*.blend"), key=lambda p: p.as_posix().lower())
    if args.match_label:
        blend_files = [
            path
            for path in blend_files
            if args.match_label.lower() in path.relative_to(root).as_posix().lower()
        ]
    if args.limit:
        blend_files = blend_files[: args.limit]

    profiles = []
    errors = []
    for path in blend_files:
        try:
            profiles.append(profile_blend(path, root))
        except Exception as exc:  # Blender files can be version-sensitive.
            errors.append({"relative_label": path.relative_to(root).as_posix(), "error": str(exc)})

    output = {
        "source_redaction": "Local absolute paths and raw assets are intentionally omitted.",
        "blend_file_count_attempted": len(blend_files),
        "profile_count": len(profiles),
        "error_count": len(errors),
        "profiles": profiles,
        "errors": errors,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: output[k] for k in ["blend_file_count_attempted", "profile_count", "error_count"]}, indent=2))


if __name__ == "__main__":
    main()

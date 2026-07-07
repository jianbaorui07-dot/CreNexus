---
name: painting-hd-batch
description: Create or guide batches of high-resolution repaired PNG assets from locally provided Chinese New Year painting exhibition photos. Use when the user asks to extract or repair individual 人物, 图案, or 场景 from 年画展陈 source photos, produce 1086x1448 paper-background PNGs, package batch outputs, or verify this specific painted-figure image style.
---

# Painting HD Batch

Use this skill to make finished assets from user-provided 年画展陈 source photos: one source image per numbered folder, plus one or more repaired high-resolution PNGs for individual people, motifs, or small scenes from that photo.

The finished look is a clean traditional Chinese 年画 / 工笔 painted asset on a light 宣纸 background, not a cropped museum photo and not a modern redraw.

## Privacy Boundary

This repository must not store source photos, generated PNGs, private reference images, or real local paths. Configure local paths outside the repository with environment variables such as:

- `PAINTING_HD_SOURCE_DIR`
- `PAINTING_HD_REFERENCE_DIR`
- `PAINTING_HD_OUTPUT_DIR`

Only run the batch workflow against files the user explicitly provides for the current task.

## Existing Workflow

Prefer an existing local project workflow before writing new code. When the workspace contains the `painting_hd_batch` helper package, use:

- `painting_hd_batch/main.py`: scans source images, prepares 1086x1448 PNG repair inputs, writes model prompts, and creates per-image folders.
- `painting_hd_batch/quality_check.py`: checks PNG existence, size, mode, and alpha.
- `painting_hd_batch/package_outputs.py`: creates per-folder ZIPs and a total ZIP.
- `painting_hd_batch/config.json`: stores source path, output path, canvas size, DPI, Photoshop preprocessing, and reference path settings.

For a quick sample run, use:

```powershell
python .\painting_hd_batch\main.py --limit 1
```

For the full configured batch, use:

```powershell
python .\painting_hd_batch\main.py
```

Only patch these scripts when the existing flow cannot cover the request.

## Target Output

Match the user-provided completed examples or the locally configured reference set in `PAINTING_HD_REFERENCE_DIR`.

Each numbered folder should contain:

- the original source image, for comparison
- one or more final PNGs named with the source stem, object type, sequence number, and a short location/subject note

Use this naming shape:

```text
画_年画展陈_002_人物01_左侧栏边粉衣女子.png
画_年画展陈_003_图案01_中央红鲤.png
画_年画展陈_005_场景01_中下骑马戏剧人物.png
```

Output PNG requirements:

- `1086x1448` pixels, portrait orientation
- RGB PNG unless the user explicitly requests true transparency
- light warm 宣纸 background with subtle texture
- full object visible and centered with balanced top/bottom margin
- no museum wall, frame, mat board, glass glare, reflection, labels, text, watermark, selection UI, or crop handles
- no full exhibition photo shrunk onto the canvas

## Object Types

Use `人物` for a single person or a tightly bound person-child pair when splitting them would damage the subject.

Use `图案` for animals, flowers, plants, decorative objects, auspicious motifs, or isolated non-human elements.

Use `场景` for a small multi-person or architectural scene where the group relationship is the subject.

Do not force every source image into one output. A dense painting may need multiple `人物`, `图案`, and `场景` PNGs.

## Generation Brief

When using an image model, provide the source photo or crop and specify the exact target object. Use a prompt with these constraints:

```text
从这张年画展陈照片中提取并修复【对象描述】。
生成独立的高清传统中国年画/工笔彩绘 PNG：1086x1448 竖版，浅暖宣纸底，主体完整居中。
保留原画中的姿态、朝向、服饰纹样、发型、表情、道具、线描和手绘设色质感。
清除展陈环境、相框、卡纸边、玻璃反光、文字、编号、水印和多余背景。
不要生成现代插画、动漫、3D、摄影、油画或写实数字绘画。
不要把整张展陈照片缩进画布；只保留指定的人物/图案/场景。
```

For small or damaged subjects, crop tightly around the object first, but include enough neighboring context to preserve pose, clothing, and occluded edges.

## Visual QA

Always inspect generated PNGs visually before calling them finished.

Reject and regenerate if:

- the output is just a resized full exhibition photo
- the subject is cropped, missing limbs/details, or no longer matches the source object
- style changed into modern illustration, anime, 3D, oil painting, or photo-realism
- glare, frame, wall, labels, UI artifacts, or source-photo perspective remains
- the paper background is too plain, too dark, or visually unlike the examples
- filename object type or location note does not match the actual subject

Run the dimension check on completed folders:

```powershell
python .\painting_hd_batch\quality_check.py <folder>
```

## Safety

Treat source photos, reference examples, and completed outputs as private local assets unless the user explicitly says they are public test files. Do not commit them, summarize private paths, or overwrite existing PNGs unless the user explicitly asks. When adding revisions, use a new filename or a clearly versioned copy.

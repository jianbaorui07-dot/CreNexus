# Codex Stable Fast 3D local bridge

Stable Fast 3D is useful when StarBridge needs a local image-to-3D asset generator before handing GLB/OBJ/FBX outputs
to Blender or another DCC tool. This repository does not redistribute the upstream project or model weights; it keeps a
small, parameterized read-only probe under `examples/stable_fast_3d_bridge/`.

## Local Workflow

```text
input image -> background removal mask -> SF3D mesh generation -> texture baking -> GLB export -> Blender cleanup
```

Configure local paths outside the repository:

```text
<LOCAL_SF3D_ROOT>
<LOCAL_CACHE_ROOT>\huggingface
<LOCAL_CACHE_ROOT>\u2net
```

## Entry Points

- `examples/stable_fast_3d_bridge/probe.py`

## Verification Notes

The public repository only verifies the read-only probe shape. Model installation, GPU compatibility, generation and
texture-baking behavior remain local manual validation and must not be described as repository-verified.

## Repository Boundary

Do not commit:

- Hugging Face tokens
- model weights or ONNX files
- `.venv`
- local generated meshes
- private source images

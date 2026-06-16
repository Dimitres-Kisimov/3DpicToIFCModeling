"""
InstantMesh (TencentARC, Apache-2.0) generative-fallback adapter.

Mirrors the run_trellis_wsl.py contract:
  python run_instantmesh_wsl.py <input_image> <output_glb>
  → prints a JSON result envelope on stdout.

InstantMesh's pipeline:
  1. Background removal (rembg)
  2. Zero123++ generates a 6-view sheet from the single input view
  3. InstantMesh's sparse-view reconstruction model produces a textured mesh
     (geometry + per-vertex / texture-map colour from the 6 views)

VRAM budget on 8 GB:
  - Zero123++ multi-view diffusion: ~3-4 GB
  - InstantMesh reconstruction: ~3-4 GB
  - Total peak ~5-6 GB (fits comfortably; not at the TRELLIS ceiling)

Safety:
  - PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True to avoid fragmentation
  - Pre-init torch BEFORE anything CUDA-allocating to catch import errors

Licence: Apache-2.0 (matches InstantMesh).
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path


os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

INSTANTMESH_ROOT = "/root/InstantMesh"
if INSTANTMESH_ROOT not in sys.path:
    sys.path.insert(0, INSTANTMESH_ROOT)


def emit_error(err_type: str, msg: str) -> None:
    print(json.dumps({
        "success": False,
        "error": {"type": err_type, "message": str(msg)[:1500]},
    }), flush=True)
    sys.exit(1)


def main(argv) -> None:
    if len(argv) < 3:
        emit_error("args", "Usage: run_instantmesh_wsl.py <input_image> <output_glb>")
    img_path, out_glb = argv[1], argv[2]
    if not os.path.exists(img_path):
        emit_error("args", f"image not found: {img_path}")
    os.makedirs(os.path.dirname(out_glb) or ".", exist_ok=True)

    # ---- Stage 0: torch sanity ----
    try:
        import torch
    except Exception as e:
        emit_error("import", f"torch import failed: {e}")
    if not torch.cuda.is_available():
        emit_error("hardware", "CUDA not available inside WSL")

    total = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
    print(f"[instantmesh-wsl] CUDA OK — {torch.cuda.get_device_name(0)}, "
          f"{total} MiB VRAM, allocator=expandable_segments", flush=True)

    # ---- Stage 1: background removal ----
    try:
        import rembg
        from PIL import Image
        with open(img_path, "rb") as fh:
            cut_bytes = rembg.remove(fh.read())
        from io import BytesIO
        img = Image.open(BytesIO(cut_bytes)).convert("RGBA")
        # InstantMesh expects a centred RGBA on a white-ish background; the
        # rembg cut is already centred enough for most product photos.
        print(f"[instantmesh-wsl] foreground segmented "
              f"({img.size[0]}x{img.size[1]} RGBA)", flush=True)
    except Exception as e:
        emit_error("unknown", f"background removal failed: {e}\n"
                               f"{traceback.format_exc()}")

    # ---- Stage 2: Zero123++ multi-view generation ----
    # InstantMesh ships a wrapper around Zero123++ that produces a 3x2 grid
    # (6 views) at 320x320 each. Loaded from sudo-ai/zero123plus-v1.2.
    try:
        from diffusers import DiffusionPipeline, EulerAncestralDiscreteScheduler
        # Load the official Zero123++ pipeline.py from a local file path —
        # the historical custom_pipeline="zero123plus" string referenced a
        # GitHub-hosted community example that has since been removed from
        # the diffusers v0.27.2 tag. We ship /root/InstantMesh/zero123plus.py
        # (copied from SUDO-AI-3D/zero123plus@main/diffusers-support).
        zero123 = DiffusionPipeline.from_pretrained(
            "sudo-ai/zero123plus-v1.2",
            custom_pipeline="/root/InstantMesh/zero123plus.py",
            torch_dtype=torch.float16,
        )
        zero123.scheduler = EulerAncestralDiscreteScheduler.from_config(
            zero123.scheduler.config, timestep_spacing="trailing",
        )
        zero123.to("cuda:0")
        torch.cuda.empty_cache()
        print(f"[instantmesh-wsl] Zero123++ loaded; "
              f"VRAM in use {torch.cuda.memory_allocated() // (1024*1024)} MiB",
              flush=True)

        # Generate 6-view sheet — fixed seed for reproducibility so we can
        # compare across runs (Zero123++ is stochastic; without a seed every
        # run gives different views and we can't tell if a quality regression
        # is from code changes or just luck).
        _g = torch.Generator(device="cuda:0").manual_seed(42)
        out = zero123(img,
                       num_inference_steps=int(
                           os.environ.get("INSTANTMESH_ZERO123_STEPS", "75")),
                       generator=_g).images[0]

        # Save Zero123++ intermediate sheet so we can see if it produced
        # plausible multi-view images of the input chair.
        debug_sheet = os.environ.get("SCS_INSTANTMESH_DEBUG_SHEET")
        if debug_sheet:
            try:
                out.save(debug_sheet)
                print(f"[instantmesh-wsl] zero123++ sheet saved → {debug_sheet}",
                      flush=True)
            except Exception as _de:
                print(f"[instantmesh-wsl] debug sheet save failed: {_de}",
                      flush=True)
        # 6-view sheet is 960x640 (3 cols x 2 rows of 320x320)
        print(f"[instantmesh-wsl] Zero123++ generated 6-view sheet "
              f"({out.size[0]}x{out.size[1]})", flush=True)

        # Free Zero123++ before loading reconstruction model — large win
        zero123.to("cpu")
        del zero123
        torch.cuda.empty_cache()
        print(f"[instantmesh-wsl] Zero123++ offloaded; "
              f"VRAM now {torch.cuda.memory_allocated() // (1024*1024)} MiB",
              flush=True)
    except torch.cuda.OutOfMemoryError as e:
        emit_error("oom", f"OOM at Zero123++: {e}")
    except Exception as e:
        emit_error("unknown", f"Zero123++ failed: {e}\n"
                               f"{traceback.format_exc()}")

    # ---- Stage 3: InstantMesh sparse-view reconstruction ----
    try:
        import numpy as np
        from omegaconf import OmegaConf
        from huggingface_hub import hf_hub_download
        from einops import rearrange
        import torchvision.transforms.v2 as v2

        # instant-mesh-base (not -large) — base has triplane_dim=40 (large=80)
        # and 12 transformer layers (large=16). Roughly 50% less peak VRAM
        # during the FlexiCubes SDF prediction. Quality is still meaningfully
        # above TripoSR (multi-view reconstruction vs single-view).
        cfg_name = os.environ.get("SCS_INSTANTMESH_VARIANT", "instant-mesh-base")
        cfg_path = f"/root/InstantMesh/configs/{cfg_name}.yaml"
        cfg = OmegaConf.load(cfg_path)
        infer_config = cfg.infer_config

        # Keep grid_res at trained value (128). Reducing it collapses the SDF
        # MLP — model was trained on 128, smaller grid produces all-positive
        # SDF and Step 3 fallback returns a cube. We solve VRAM the proper
        # way: chunk the MLP forward over points (further down).
        grid_res = int(os.environ.get("SCS_INSTANTMESH_GRID_RES", "128"))
        cfg.model_config.params.grid_res = grid_res
        print(f"[instantmesh-wsl] grid_res override: {grid_res}", flush=True)

        # Load the reconstruction model
        from src.utils.train_util import instantiate_from_config
        from src.utils.camera_util import get_zero123plus_input_cameras
        model = instantiate_from_config(cfg.model_config)
        ckpt_name = ("instant_mesh_base.ckpt" if cfg_name.endswith("base")
                     else "instant_mesh_large.ckpt")
        weight_path = hf_hub_download(
            repo_id="TencentARC/InstantMesh",
            filename=ckpt_name,
            repo_type="model",
        )
        state_dict = torch.load(weight_path, map_location="cpu")["state_dict"]
        model.load_state_dict(state_dict, strict=False)
        model = model.to("cuda:0")
        model.eval()
        # FlexiCubes init — instant-mesh-* configs always use it
        if hasattr(model, "init_flexicubes_geometry"):
            try:
                model.init_flexicubes_geometry(
                    torch.device("cuda:0"),
                    fovy=30.0,
                )
            except Exception as ie:
                print(f"[instantmesh-wsl] flexicubes init: {ie}", flush=True)
        print(f"[instantmesh-wsl] reconstruction model loaded; "
              f"VRAM {torch.cuda.memory_allocated() // (1024*1024)} MiB",
              flush=True)

        # ── Monkey-patch the FlexiCubes SDF/deformation MLP to chunk over
        # points. The model trained at grid_res=128 has 129³ ≈ 2.1 M points,
        # which the SDF MLP processes in one shot — fits a 24 GB card but not
        # 8 GB. We split sampled_features into chunks of N points, run each
        # through the original MLPs, concat the outputs. Same arithmetic,
        # ~8× lower peak VRAM at this stage.
        _chunk = int(os.environ.get("SCS_INSTANTMESH_MLP_CHUNK", "262144"))
        _decoder = model.synthesizer.decoder
        _orig_geometry = _decoder.get_geometry_prediction

        def _chunked_geometry(sampled_features, flexicubes_indices,
                                _decoder=_decoder, _chunk=_chunk):
            # sampled_features: (N, n_planes, M, C)
            N, n_planes, M, C = sampled_features.shape
            sf = sampled_features.permute(0, 2, 1, 3).reshape(N, M, n_planes * C)

            # SDF + deformation MLPs — chunk over the M dimension.
            sdf_parts, def_parts = [], []
            for i in range(0, M, _chunk):
                sub = sf[:, i:i + _chunk]
                sdf_parts.append(_decoder.net_sdf(sub))
                def_parts.append(_decoder.net_deformation(sub))
            sdf = torch.cat(sdf_parts, dim=1)
            deformation = torch.cat(def_parts, dim=1)

            # Weight MLP — original code does:
            #   grid_features = index_select(sf, flexicubes_indices, dim=1)
            #   grid_features = reshape(N, num_cubes, 8*C')
            #   weight = net_weight(grid_features) * 0.1
            # For grid_res=128 the gathered tensor is ~8 GB, blowing the
            # 8 GB VRAM. We chunk over the num_cubes dim — gather + reshape +
            # MLP forward per chunk, then concat.
            num_cubes = flexicubes_indices.shape[0]
            cube_chunk = max(1, _chunk // 8)
            weight_parts = []
            for i in range(0, num_cubes, cube_chunk):
                idx_sub = flexicubes_indices[i:i + cube_chunk]
                gf = torch.index_select(
                    input=sf, index=idx_sub.reshape(-1), dim=1)
                gf = gf.reshape(sf.shape[0], idx_sub.shape[0],
                                 idx_sub.shape[1] * sf.shape[-1])
                weight_parts.append(_decoder.net_weight(gf) * 0.1)
            weight = torch.cat(weight_parts, dim=1)

            return sdf, deformation, weight

        _decoder.get_geometry_prediction = _chunked_geometry
        print(f"[instantmesh-wsl] SDF/deformation MLP chunked at "
              f"{_chunk} points/chunk", flush=True)

        # Slice the Zero123++ output sheet into 6 individual 320x320 tiles.
        # Sheet is 640 wide × 960 tall — 2 cols × 3 rows of 320x320.
        # InstantMesh reshapes via einops: '(n h) (m w) -> (n m) h w', n=3, m=2
        sheet = np.asarray(out, dtype=np.float32) / 255.0     # (960, 640, 3)
        sheet = torch.from_numpy(sheet).permute(2, 0, 1).contiguous().float()
        # (3, 960, 640) -> (6, 3, 320, 320)
        images = rearrange(sheet, "c (n h) (m w) -> (n m) c h w", n=3, m=2)
        images = images.unsqueeze(0).to("cuda:0")            # (1, 6, 3, 320, 320)
        images = v2.functional.resize(images, 320, interpolation=3,
                                       antialias=True).clamp(0, 1)

        # Zero123++ camera config — 6 fixed orbiting views around the object
        input_cameras = get_zero123plus_input_cameras(
            batch_size=1, radius=4.0,
        ).to("cuda:0")

        with torch.no_grad():
            planes = model.forward_planes(images, input_cameras)
            mesh_out = model.extract_mesh(
                planes,
                use_texture_map=False,
                **infer_config,
            )

        # extract_mesh returns a tuple when use_texture_map=False:
        # (vertices, faces, vertex_colors) or (vertices, faces) depending on
        # build. Normalize both shapes.
        if isinstance(mesh_out, tuple):
            if len(mesh_out) == 3:
                _verts, _faces, _vcols = mesh_out
            else:
                _verts, _faces = mesh_out[:2]
                _vcols = None
        else:
            _verts = mesh_out.vertices
            _faces = mesh_out.faces
            _vcols = getattr(mesh_out, "vertex_colors", None)

        print(f"[instantmesh-wsl] mesh extracted: "
              f"{_verts.shape[0]} verts, {_faces.shape[0]} faces", flush=True)
    except torch.cuda.OutOfMemoryError as e:
        emit_error("oom", f"OOM at InstantMesh reconstruction: {e}")
    except Exception as e:
        emit_error("unknown", f"InstantMesh reconstruction failed: {e}\n"
                               f"{traceback.format_exc()}")

    # ---- Stage 4: export to GLB ----
    try:
        import trimesh as _tm
        verts = _verts.detach().cpu().numpy() if hasattr(_verts, "detach") else _verts
        faces = _faces.detach().cpu().numpy() if hasattr(_faces, "detach") else _faces
        out_mesh = _tm.Trimesh(vertices=verts, faces=faces, process=False)

        if _vcols is not None:
            colours = _vcols.detach().cpu().numpy() \
                if hasattr(_vcols, "detach") else _vcols
            if colours.shape[0] == verts.shape[0]:
                if colours.dtype != np.uint8:
                    colours = (colours.clip(0, 1) * 255).astype(np.uint8)
                if colours.shape[-1] == 3:
                    alpha = np.full((colours.shape[0], 1), 255, dtype=np.uint8)
                    colours = np.concatenate([colours, alpha], axis=1)
                out_mesh.visual.vertex_colors = colours

        out_mesh.export(out_glb)
        size = os.path.getsize(out_glb)
        print(f"[instantmesh-wsl] GLB saved: {size} bytes", flush=True)
    except Exception as e:
        emit_error("unknown", f"GLB export failed: {e}\n"
                               f"{traceback.format_exc()}")

    print(json.dumps({
        "success": True,
        "output_path": out_glb,
        "glb_size_bytes": size,
        "source": "InstantMesh (TencentARC) — Zero123++ multi-view + sparse recon",
        "license": "Apache-2.0",
        "attribution": "https://github.com/TencentARC/InstantMesh",
        "method": "instantmesh+zero123plus+rembg",
    }), flush=True)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except SystemExit:
        raise
    except Exception as e:
        emit_error("unknown", f"top-level: {e}\n{traceback.format_exc()}")

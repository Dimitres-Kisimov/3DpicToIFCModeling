"""
InstantMesh inference script - fast depth-based 3D mesh from a single image.
Uses DPT depth estimation to build a colored 3D mesh.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit, generate_depth_mesh


def generate_mesh_instantmesh(image_path, output_path):
    try:
        log("InstantMesh: fast depth-based mesh generation", "info")
        log(f"Input: {image_path}", "info")

        glb_data = generate_depth_mesh(
            image_path,
            resolution=64,
            model_name="Intel/dpt-hybrid-midas",
        )

        with open(output_path, "wb") as f:
            f.write(glb_data)

        log(f"GLB written: {len(glb_data)} bytes", "info")

        return {
            "model": "instantmesh",
            "image_path": image_path,
            "output_path": output_path,
            "glb_size_bytes": len(glb_data),
            "resolution": 64,
            "method": "dpt-depth-mesh",
        }

    except Exception as e:
        error_exit(f"InstantMesh inference failed: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: run_instantmesh.py <input_image> <output_glb>")

    input_image = sys.argv[1]
    output_glb = sys.argv[2]

    if not os.path.exists(input_image):
        error_exit(f"Input image not found: {input_image}")

    result = generate_mesh_instantmesh(input_image, output_glb)
    success_exit(result)

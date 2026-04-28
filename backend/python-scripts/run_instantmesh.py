"""
InstantMesh — fast segmented depth mesh (YOLO + DPT, 64px resolution).
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from inference_base import log, error_exit, success_exit, generate_segmented_depth_mesh

def generate_mesh_instantmesh(image_path, output_path):
    try:
        log("InstantMesh: YOLO segmentation + depth mesh (fast)", "info")
        glb_data = generate_segmented_depth_mesh(image_path, resolution=128,
                                                  depth_model="Intel/dpt-hybrid-midas")
        with open(output_path, "wb") as f:
            f.write(glb_data)
        return {"model": "instantmesh", "image_path": image_path,
                "output_path": output_path, "glb_size_bytes": len(glb_data),
                "resolution": 64, "method": "yolo-seg+dpt"}
    except Exception as e:
        error_exit(f"InstantMesh failed: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        error_exit("Usage: run_instantmesh.py <input_image> <output_glb>")
    if not os.path.exists(sys.argv[1]):
        error_exit(f"Input image not found: {sys.argv[1]}")
    success_exit(generate_mesh_instantmesh(sys.argv[1], sys.argv[2]))

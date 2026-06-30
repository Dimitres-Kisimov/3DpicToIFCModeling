"""rerender_inputs.py — re-render every metric input from its GT mesh so the FULL piece of
furniture is in frame with generous white margin (NO cut edges). Fixes the tight 256px ABO
thumbnails that sliced the furniture at the borders. Run LOCALLY.

For each deliverable/cloud_bundle/gt/<type>.glb:
  render the textured mesh -> composite on white -> crop to content -> re-pad so the object
  occupies ~60% of a 768x768 white canvas (=> ~20% white margin every side) -> inputs/<type>.png
"""
import io, numpy as np
from pathlib import Path
from PIL import Image
import trimesh

GT = Path("deliverable/cloud_bundle/gt")
INP = Path("deliverable/cloud_bundle/inputs")
INP.mkdir(parents=True, exist_ok=True)

OBJ_FRAC = 0.60      # object = 60% of frame -> 20% margin each side
SIDE = 768

def content_bbox(rgb):
    fg = np.abs(rgb.astype(int) - 255).sum(2) > 30
    ys, xs = np.where(fg)
    if len(xs) == 0:
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1

for glb in sorted(GT.glob("*.glb")):
    try:
        m = trimesh.load(glb, force="mesh")
        scene = m.scene()
        png = scene.save_image(resolution=(720, 720))
        img = Image.open(io.BytesIO(png)).convert("RGBA")
        comp = Image.alpha_composite(Image.new("RGBA", img.size, (255, 255, 255, 255)), img).convert("RGB")
        bb = content_bbox(np.array(comp))
        if bb is None:
            print(f"{glb.name}: EMPTY render, skipped"); continue
        crop = comp.crop(bb)
        side = int(max(crop.size) / OBJ_FRAC)
        canvas = Image.new("RGB", (side, side), (255, 255, 255))
        canvas.paste(crop, ((side - crop.width) // 2, (side - crop.height) // 2))
        canvas = canvas.resize((SIDE, SIDE), Image.LANCZOS)
        canvas.save(INP / (glb.stem + ".png"))
        # verify margin
        a = np.array(canvas).astype(int)
        fg = np.abs(a - 255).sum(2) > 30
        ys, xs = np.where(fg)
        l, r, t, b = xs.min(), SIDE - 1 - xs.max(), ys.min(), SIDE - 1 - ys.max()
        minm = 100 * min(l, r, t, b) / SIDE
        print(f"{glb.stem:14} -> {SIDE}x{SIDE}  margins% L{100*l//SIDE} R{100*r//SIDE} T{100*t//SIDE} B{100*b//SIDE}  min={minm:.1f}%  {'OK' if minm>=8 else 'CHECK'}")
    except Exception as e:
        print(f"{glb.name}: render FAIL {e!r}")
print("done -> deliverable/cloud_bundle/inputs/")

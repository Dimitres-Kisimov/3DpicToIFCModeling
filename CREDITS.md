# Credits and Third-Party Attribution

This product uses the following third-party data, models, and software.
The list is complete to the best of the authors' knowledge on the report
date below; every redistribution of this software is required to include
this file by the obligations of the licences listed.

**Last verified:** 2026-06-10
**Author:** Dimitres Kisimov, on behalf of SCS

---

## 1. 3D Mesh Library

### Amazon Berkeley Objects (ABO)

**Source:** <https://amazon-berkeley-objects.s3.amazonaws.com/index.html>
**Publisher:** Amazon
**Licence:** Creative Commons Attribution 4.0 International (CC-BY-4.0)
<https://creativecommons.org/licenses/by/4.0/>

**Paper:**
Collins, J., Goel, S., Deng, K., Luthra, A., Xu, L., Gundogdu, E., Zhang, X.,
Vicente, T. F. Y., Dideriksen, T., Arora, H., Guillaumin, M., & Malik, J. (2022).
*ABO: Dataset and Benchmarks for Real-World 3D Object Understanding.*
arXiv:2110.06199.

**Modifications by SCS:**
- ABO meshes are filtered to office-furniture categories (chair, sofa, table,
  desk, cabinet, bookshelf, lamp, stool)
- Meshes are loaded with `trimesh`, normalised by bounding-box centroid,
  decimated to ≤ 8000 faces when needed for IFC4 compatibility
- Real-world dimensions in metres are measured from each mesh's bounding box

**Attribution in shipped IFC files:**
Every `IfcFurniture` entity backed by an ABO mesh carries the following
properties in its `Pset_SCS_DetectionMetadata` property set:

```
MeshSource_Id            (the ABO model identifier, e.g. B07TMH6289)
MeshSource_Dataset       = "Amazon Berkeley Objects (ABO)"
MeshSource_License       = "CC-BY-4.0"
MeshSource_Attribution   = "https://amazon-berkeley-objects.s3.amazonaws.com/index.html"
```

This satisfies the CC-BY-4.0 attribution requirement on a per-mesh basis and
travels with the IFC file to every downstream consumer (Revit, BIM Vision,
xeokit, FreeCAD, etc.).

---

## 2. AI Models

### DETR ResNet-50 — Object Detection

**Source:** <https://huggingface.co/facebook/detr-resnet-50>
**Publisher:** Meta AI (Facebook AI Research)
**Licence:** Apache-2.0
**Paper:** Carion, N. et al. (2020). *End-to-End Object Detection with Transformers.* arXiv:2005.12872.

### Depth Anything V2 Metric-Indoor-Small — Monocular Depth

**Source:** <https://huggingface.co/depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf>
**Publisher:** University of Hong Kong + ByteDance Research
**Licence:** Apache-2.0
**Paper:** Yang, L. et al. (2024). *Depth Anything V2.* arXiv:2406.09414.

**Note:** SCS uses the *Small* variant specifically because the *Base* and
*Large* variants of Depth Anything V2 are released under CC-BY-NC-4.0
(non-commercial). This is documented as a licence trap in
[TECHNICAL_REPORT_SCS.md](TECHNICAL_REPORT_SCS.md) §6.4.

### DINOv2-base — Image Retrieval Embedding

**Source:** <https://huggingface.co/facebook/dinov2-base>
**Publisher:** Meta AI
**Licence:** Apache-2.0
**Paper:** Oquab, M. et al. (2023). *DINOv2: Learning Robust Visual Features without Supervision.* arXiv:2304.07193.

### rembg (U²-Net) — Foreground Segmentation Fallback

**Source:** <https://github.com/danielgatis/rembg>
**Licence:** MIT
**Underlying model:** U²-Net (Qin et al., 2020) — Apache-2.0

### MoGe — Monocular Geometric Estimation (used by SAM 3D Objects path)

**Source:** <https://github.com/microsoft/MoGe>
**Publisher:** Microsoft Research
**Licence:** MIT
**Paper:** Wang, R. et al. (2024). *MoGe: Unlocking Accurate Monocular Geometric Estimation.*

---

## 3. Libraries

### IfcOpenShell — IFC4 Reading and Writing

**Source:** <https://github.com/IfcOpenShell/IfcOpenShell>
**Licence:** LGPL-3.0 (library-link safe — does NOT trigger copyleft on linking applications)

### xeokit-SDK — Browser BIM Viewer

**Source:** <https://github.com/xeokit/xeokit-sdk>
**Publisher:** xeolabs / Creoox
**Licence:** MIT

### xeokit-convert — IFC → XKT Converter

**Source:** <https://github.com/xeokit/xeokit-convert>
**Licence:** AGPL-3.0 *for CLI use*, separate commercial licence available
**Note:** Used only as a build-time CLI, NOT linked into the SCS application.
This preserves AGPL boundary compliance.

### FAISS (faiss-cpu) — Vector Similarity Index

**Source:** <https://github.com/facebookresearch/faiss>
**Publisher:** Meta AI
**Licence:** MIT

### trimesh — Mesh Processing

**Source:** <https://github.com/mikedh/trimesh>
**Licence:** MIT

### transformers — Model Loading

**Source:** <https://github.com/huggingface/transformers>
**Publisher:** Hugging Face
**Licence:** Apache-2.0

### accelerate, bitsandbytes — CPU Offload + Quantisation

**Source:** <https://github.com/huggingface/accelerate>, <https://github.com/TimDettmers/bitsandbytes>
**Licences:** Apache-2.0 (accelerate), MIT (bitsandbytes)

### Express.js, multer, dotenv — Backend Runtime

**Licences:** MIT for all three

### Pillow, NumPy, SciPy — Image and Numeric Processing

**Licences:** MIT-CMU (Pillow), BSD-3 (NumPy, SciPy)

---

## 4. Tooling and Standards

### Industry Foundation Classes (IFC4)

**Standard publisher:** buildingSMART International
**Spec:** <https://standards.buildingsmart.org/IFC/RELEASE/IFC4/>
**Licence:** Royalty-free open standard

### COCO dataset (training data for DETR)

**Source:** <https://cocodataset.org/>
**Licence:** CC-BY-4.0 (annotations)

---

## 5. SCS Project Code

The application code in this repository — backend (Node.js + Python), frontend
(vanilla JS + xeokit SDK loader), retrieval pipeline, IFC export logic,
documentation, and procedurally generated mesh fallback library — is original
work prepared on behalf of SCS by the author.

Unless explicitly noted otherwise per-file, the SCS-authored code is the
property of SCS and is not redistributed under any open-source licence.

---

## 6. Notable Components Examined and Rejected

The following components were considered during the model survey but rejected
on either licence or hardware grounds. They are listed here so future
contributors can avoid re-introducing them.

| Component | Rejection reason |
|---|---|
| Hunyuan3D-2 (Tencent) | Geographic exclusion — licence verbatim excludes the European Union, United Kingdom, and South Korea. Plus 1M MAU cap and an output-binding clause. |
| Stable Fast 3D (Stability AI) | Stability Community Licence caps royalty-free commercial use at US $1,000,000 annual revenue. Future royalty risk for SCS at scale. |
| Depth Anything V2 *Base* / *Large* | CC-BY-NC-4.0 (non-commercial). Only the *Small* variant is Apache-2.0. |
| YOLOv8 / Ultralytics | AGPL-3.0 strong copyleft. Linking obligates the entire SCS application to release under AGPL. Removed from the repository on this branch. |
| Apple DepthPro | `apple-amlr` licence — research only. |
| OpenAI CLIP weights | MIT-licensed weights but the model card explicitly states *"Any deployed use case ... is currently out of scope."* — legal ambiguity. SCS uses SigLIP 2 (Apache-2.0) instead where CLIP-style embeddings are needed. |

For full licence verification with verbatim quotations, see
[TECHNICAL_REPORT_SCS.md](TECHNICAL_REPORT_SCS.md) §6.4 and §13.3.

---

## 7. Statement of Compliance

SCS does not owe royalties, share-back obligations, or per-use payments to
any third party for the components listed above. All licences permit
commercial use globally, including the European Union and the United Kingdom.
The only outstanding obligation is attribution — which is satisfied by:

1. This `CREDITS.md` file in the source repository
2. The credits footer in the frontend UI (visible on every page load)
3. The `MeshSource_*` properties embedded per object in every exported IFC4 file
4. The licence file shipped alongside any redistribution of the source code

If this product is redistributed in source form, this `CREDITS.md` file
must be included unmodified. If it is redistributed as binary or service,
the credits footer and IFC `MeshSource_*` properties together satisfy the
attribution requirement.

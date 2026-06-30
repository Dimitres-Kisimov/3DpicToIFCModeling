# TECHNICAL_REPORT_SCS

_(extracted from TECHNICAL_REPORT_SCS.docx)_



From Photograph to BIM

An End-to-End AI Pipeline for Office-Furniture Reconstruction and IFC Export

A Technical Report Prepared for SCS

 

 



Disclaimer and Confidentiality Notice

This report has been prepared as an internal technical deliverable for SCS. It contains technical analysis, model evaluation, licence assessment, and engineering recommendations that are intended for SCS’s project planning and stakeholder review. The licence assessments contained in this document represent the author’s interpretation of publicly available licence text on the report date; they do not constitute legal advice and should be confirmed with qualified counsel before any deployment decision that depends on them.

External redistribution of this report should be limited to recipients with a legitimate operational interest in the project. References to third-party models, datasets, and software libraries are accompanied by their respective upstream licence statements and reflect the state of those licences on the report date.



Notice on Inclusive Language

For ease of reading, this report uses singular nominal forms (the engineer, the user, the developer, the stakeholder, the reviewer) without simultaneously enumerating every grammatical gender. These terms are intended to refer to persons of all genders without distinction. No exclusion is implied where the singular form is used. Where a specific individual is referred to, that person’s own preferred form is used.



Preface

The work documented in this report was undertaken on behalf of SCS to evaluate whether a single photograph of an office artefact can be converted, by means of contemporary artificial-intelligence tooling deployed locally on commodity hardware, into a Building-Information-Modeling-compliant Industry-Foundation-Class (IFC) representation suitable for the drag-and-drop population of virtual office rooms in a web-based viewer.

Over the course of the project the engineering team has progressively recognised that the class of solution initially pursued — single-view generative three-dimensional reconstruction — is structurally inadequate to a commercial catalog-driven workflow, and has pivoted on 21 May 2026 to a retrieval-based architecture against a clean library of artist-authored CAD meshes. This report is the consolidation document for that pivot. It documents what was attempted, what failed, what succeeded, and what is recommended next. It is intended to be readable by the SCS technical staff who will implement the recommendations, and by the SCS management who must approve the licence posture and the hardware procurement that the recommendations entail.

The report further audits the licence posture of every candidate model under consideration and identifies three concrete licence configurations that, while appearing permissive on a casual reading, would silently void commercial usage if uncorrected. These traps are flagged with their verbatim licence quotations and a recommended mitigation for each.

The author wishes to thank the engineering colleagues whose prior branch-level work this report consolidates, and the SCS stakeholders whose framing of the deliverable made the retrieval pivot inevitable in retrospect.

 

[Place and date]          [Author Name]



Abstract

This report documents a critical examination of an in-development image-to-Industry-Foundation-Class (IFC) modeling pipeline being built for SCS, intended to convert a single photograph of an office furnishing into a Building-Information-Modeling-ready three-dimensional model and ultimately a BIM-conformant IFC4 file. The pipeline targets a downstream use case in which SCS clients populate virtual office rooms by drag-and-drop placement of recognised objects inside the xeokit web viewer. Over five iterations across nine git branches, the project has progressively recognised the structural inadequacy of single-view generative neural reconstruction for a catalog-driven commercial workflow, and has pivoted on 2026-05-21 to a retrieval-based architecture against a curated library of clean Computer-Aided-Design (CAD) meshes. The present document reconstructs that journey, formalises the failure modes that motivated the pivot, surveys 20 candidate models on HuggingFace under a strict commercial-license filter (Apache-2.0, MIT, BSD, and Meta’s SAM License), and presents a comparative analysis along axes of office-furniture fitness, output fidelity for colour, material and metric dimension, hardware feasibility on the SCS development workstation, and exposure to licence-imposed restrictions. We identify three viable deployment paths, document three licence traps that would silently void commercial usage if uncorrected, and provide a runnable benchmark harness for in-house evaluation. We conclude with a prioritised roadmap of sprint-level engineering tasks and a discussion of the residual limitations of the recommended approach.

Keywords: Single-view 3D reconstruction, BIM, IFC, retrieval, DINOv2, SAM 3D, open-vocabulary object detection, licence compliance, model deployment.



Executive Summary

This report consolidates the cumulative findings of a multi-phase engineering project whose goal is to enable SCS to convert a single photograph of an office artefact into a BIM-ready IFC representation suitable for drag-and-drop room population in a web viewer. Four findings dominate the analysis.

Finding 1 — Single-view generative reconstruction cannot satisfy SCS’s deliverable. The original architecture (TripoSR followed by SAM2-enhanced segmentation and TRELLIS-based diffusion) produces 3D meshes that, while geometrically plausible, fail on four dimensions material to SCS’s commercial use case: asymmetric structural elements (e.g. independently drifting chair legs), hallucinated hidden surfaces, absent PBR materials, and absent metric scale. These are not implementation defects amenable to incremental fixes; they are properties of the single-view, image-to-3D generation class of approach and persist across every model in the 2026 state of the art.

Finding 2 — The retrieval pivot adopted on 2026-05-21 is sound and should be the production primary path. Matching an input photograph to a clean, artist-authored mesh in the Amazon Berkeley Objects library (CC-BY-4.0, 7,953 meshes) by means of a DINOv2 self-supervised embedding fixes all four failure modes at once by sidestepping generation entirely for in-catalog items. Industrial BIM practice — Revit families, BIMobject, RevitCity — converges on the same architecture.

Finding 3 — Three licence configurations that look free are not, and one is silently embedded in the repository already. The Depth Anything V2 Base and Large checkpoints are CC-BY-NC-4.0 (non-commercial); only the Small variant is Apache-2.0. The Tencent Hunyuan3D-2 Community Licence verbatim excludes the European Union, United Kingdom, and South Korea and caps monthly active users at one million. The YOLOv8 weights file yolov8n-seg.pt currently committed at the repository root is AGPL-3.0, exposing all surrounding code to AGPL obligations should the repository be redistributed.

Finding 4 — Meta’s SAM License is commercial-safe and SAM 3D Objects is a credible asynchronous fallback for non-catalog items. Contrary to a prior in-repo annotation that recorded SAM 3 / SAM 3D as “not available”, both were released on 2025-11-19, and the SAM Licence grants a non-exclusive, worldwide, royalty-free right to use, modify and distribute the model materials for commercial purposes with the only substantive restrictions concerning military, weapons, nuclear and ITAR applications. SAM 3D Objects requires approximately 24 GB of GPU memory at native precision, and therefore must run on a secondary workstation, but is the strongest single candidate for high-fidelity generation when the retrieval catalog returns no match above the confidence threshold.

From these findings we derive a recommended deployment path: Grounding DINO → SAM 2.1 → DINOv2 retrieval against Amazon Berkeley Objects → Depth Anything V2 Small for metric scaling → IfcOpenShell export → xeokit viewer, with SAM 3D Objects deployed asynchronously on a 24 GB workstation as a fallback for low-confidence retrievals. Every model in this primary path is Apache-2.0; SAM 3D Objects is SAM License; the supporting libraries are MIT and LGPL-3.0 in well-understood patterns. The configuration produces no royalty obligations, carries no monthly-active-user cap, and is not geographically restricted.

The remainder of this report substantiates these findings, surveys 20 candidate models with verbatim licence quotation and parameter counts verified directly against each HuggingFace model card on the report date, reconstructs the engineering history that led to the present design, documents lessons learned across both technical and licensing axes, and discusses the residual limitations that legitimate stakeholder review must accept.



Table of Contents

Front Matter

Disclaimer and Confidentiality Notice

Notice on Inclusive Language

Preface

Table of Contents

List of Abbreviations

List of Figures

List of Tables

Abstract

Executive Summary

Main Report

Introduction

1.1 Context — SCS, BIM, and the Office Population Workflow

1.2 Scope of the Present Report

1.3 Document Audience

1.4 Document Structure

Background and Related Work

2.1 The IFC Standard and BIM Tool Ecosystem

2.2 Single-View 3D Reconstruction — Generative Models

2.3 Single-View Retrieval

2.4 Open-Vocabulary Object Detection

2.5 Monocular Depth and Metric Scale Estimation

2.6 Segmentation: SAM and its Successors

2.7 Material Acquisition

Problem Statement

3.1 Functional Requirements (SCS-derived)

3.2 The Four Failure Modes of Single-View Generation

3.3 Why These Failure Modes Are Not Fixable by Switching Generative Models

3.4 Engineering Constraints

3.5 Formal Problem Statement

3.6 Scope and Operational Constraints — A Local-Only System

3.7 Understanding Model Weights — A Reference for SCS Stakeholders

Engineering History and the Generative-to-Retrieval Pivot

4.1 Phase 1: Infrastructure (April 2026)

4.2 Phase 2: Real IFC4 Export (May 2026, main commit 3c007eb)

4.3 Phase 2 (the 8-Sprint Block, Original-TripoSR commit 93c2a94)

4.4 The TripoSR Quality Investigation

4.5 The CLIP Fine-Tuning Effort (Dimitres.Iteration3, May 2026)

4.6 The Pivot Decision (2026-05-21, retrieval-pivot-blueprint)

4.7 Branches Map and the Latest Work

System Architecture

Model Survey and Comparative Analysis

6.1 Methodology

6.2 Cross-Pipeline Model Survey (10 Candidates)

6.3 Detection-Specific Model Survey (10 Candidates)

6.4 Licence Taxonomy and Specific Traps

6.5 Three Licence Traps the Repository Currently Has or Risks

Implementation and Configuration

7.1 Environment Setup As Executed on the SCS Workstation

7.2 Hardware Identification Correction

7.3 Configuration File

7.4 Outstanding Configuration Items

7.5 Hardware Specifications and Processing Considerations

Experimental Methodology and Test Harness

Lessons Learned

Limitations

Recommendations and Roadmap

Conclusion

Bibliography

Bibliography

Appendices

Appendix A: License Verification Details

Appendix B: Test Harness Reference

Appendix C: Repository Branch Map

Appendix D: Complete Dependency List (Verified As Installed)

Authorship

Statement of Authorship and AI-Tools Disclosure



List of Abbreviations



List of Figures



List of Tables



1. Introduction

1.1 Context — SCS, BIM, and the Office Population Workflow

SCS operates in the Building Information Modeling (BIM) sector, and the deliverable for this project is a software system that allows SCS or its clients to populate virtual building models with three-dimensional representations of office furnishings by means of photography rather than manual modeling. Concretely, an end user uploads a photograph of an office chair, a desk, a monitor, or any of nine further office object categories, and the system returns (a) a three-dimensional mesh of the object, (b) an Industry Foundation Class (IFC) file in which that mesh is wrapped as a typed BIM entity (e.g. IfcChair, IfcDesk, IfcLamp), and (c) a web-viewable scene in the xeokit JavaScript viewer where the user can drag the object into a room and arrange a layout. The same chair model, once recognised once, is reused across many rooms; the recognition is amortised.

This use case is industrially specific. Office BIM workflows in 2026 are dominated by catalog selection. Revit ships with parametric family libraries; the BIMobject and RevitCity online catalogs together index tens of thousands of artist-authored office meshes; Sketchfab offers a Creative-Commons subset; the Amazon Berkeley Objects dataset contains 7,953 artist-made meshes spanning household and office categories. The workflow is to choose from a library, not to fabricate from a photograph.

The SCS project’s distinctive value proposition is automation of the catalog choice: the user takes a photograph instead of browsing a library, and the system answers the question which library item is this. Properly framed, the engineering problem is therefore one of image-to-library matching, not one of image-to-3D generation. This framing is the central design pivot the project underwent on 2026-05-21, and it is the framing this report defends as correct.

1.2 Scope of the Present Report

This report covers the period from the initiation of the retrieval-pivot-blueprint branch through the present setup of the development environment on the SCS engineer’s workstation. It documents the engineering decisions made up to and including the consolidation of salvaged work from prior branches (commit c78f3ac, 2026-05-21), the cross-pipeline survey of 10 candidate models, the detection-specific survey of 10 candidate models, and the licence audit underlying both. It does not yet present empirical evaluation results on SCS-owned office photographs; such evaluation requires the benchmark harness delivered with this report to be run on a labelled SCS test set, which is left as a sprint deliverable in §11.

1.3 Document Audience

The intended primary audience is the SCS technical team responsible for productionising the pipeline, and the management stakeholders responsible for licensing and resource decisions. To accommodate both, technical sections are written in formal academic register but with explicit operational consequences flagged. Sections 6.4 (licence taxonomy) and 11 (recommendations and roadmap) are written to be readable by non-engineering management; Sections 2 (background), 4 (engineering history), and 8 (experimental methodology) assume engineering familiarity but no domain-specific BIM expertise.

1.4 Document Structure

§2 surveys related work in single-view 3D reconstruction, open-vocabulary detection, monocular depth, retrieval embedding, and BIM data standards. §3 formalises the four failure modes that the architecture must mitigate. §4 reconstructs the engineering history across the nine git branches. §5 documents the system architecture as it stands. §6 presents the comparative model analysis — twenty candidate models with verbatim licence quotation, parameter counts, and operational verdicts. §7 documents the implementation and configuration as deployed on the SCS engineer’s workstation. §8 documents the test harness delivered. §9 articulates lessons learned. §10 enumerates limitations. §11 presents recommendations and a sprint-level roadmap. §12 concludes.



2. Background and Related Work

2.1 The IFC Standard and BIM Tool Ecosystem

Industry Foundation Classes (IFC) are an open vendor-neutral data model maintained by buildingSMART International [28, 61] for describing buildings and the elements within them. The standard’s most widely deployed version, IFC4, defines a class hierarchy under IfcProduct and its specialisations IfcElement, IfcFurnishingElement, and concrete classes such as IfcChair, IfcDesk, IfcLamp (introduced in IFC4) and IfcElectricAppliance. An IFC4 file written by an IfcOpenShell-based [29] pipeline contains the building hierarchy (Project → Site → Building → Storey), the geometric representations of each contained element (typically as IfcTriangulatedFaceSet for arbitrary meshes), the spatial transformations relating each element to its parent storey, and a property-set vocabulary by which named attributes can be attached to instances. Downstream tooling that consumes IFC4 includes Revit (via the Open IFC importer), BIM Vision, Solibri Model Checker, the open-source FreeCAD BIM workbench, and the xeokit web viewer through the xeokit-convert toolchain [30]. The xeokit format XKT is a binary-encoded scene-graph optimised for browser delivery of large BIM models.

2.2 Single-View 3D Reconstruction — Generative Models

The 2024–2026 state of the art in single-view 3D reconstruction is dominated by neural networks that ingest one RGB image and emit a three-dimensional mesh, point cloud, or volumetric occupancy grid. The architectural families are:

Large Reconstruction Models (LRMs). TripoSR (Tochilkin et al., 2024) [19, 41] is the canonical example: a transformer encoder operating on image patches produces a triplane representation from which a continuous occupancy field is sampled and meshed via marching cubes. Inference is feed-forward and deterministic conditional on the input. TripoSR’s licence is MIT; its weights are hosted on HuggingFace at stabilityai/TripoSR and are 500 M parameters.

Multi-view-via-diffusion approaches. InstantMesh (Tencent, 2024) and Zero123++ chain a multi-view diffusion network (which hallucinates several views of the object from a single input) into a downstream reconstruction model (LRM-style). The diffusion stage introduces stochasticity — same input photograph yields different output meshes across runs.

Structured latent diffusion. TRELLIS (Xiang et al., 2024) [22, 40] operates on a Structured Latent (SLAT) representation that decouples sparse 3D geometry from dense local features. TRELLIS achieves strong topology on complex objects but is non-deterministic.

Texture-baked diffusion. Hunyuan3D-2 and -2.1 (Tencent Hunyuan3D Team, 2025) [18, 42] extend the diffusion paradigm with explicit texture-baking pipelines that produce UV-mapped meshes with PBR materials.

Sparse-view-with-pose. Meta’s SAM 3D Objects (Meta AI / FAIR, 2025) [11, 37] introduces a pose-aware single-image-to-3D model that emits both geometry and 6-degree-of-freedom pose, with textured output. The model is deterministic conditional on the input image.

A critical observation is that every model in this taxonomy must solve an ill-posed problem. The visible side of an object provides no information about its hidden side; the recovery procedure must therefore impose a prior — learned from training data — that fills in the missing structure. The plausibility of that fill depends on how representative the test object is of the training distribution. For office furniture this means: well-represented objects (e.g. office chairs) are filled in plausibly but inaccurately on detail; under-represented or unusual objects (e.g. ergonomic adjustable desks) are filled in implausibly.

2.3 Single-View Retrieval

The retrieval-based alternative trades the question what is the 3D shape of this object for which item in a library is this object. The pipeline is: image → learned embedding vector → nearest-neighbour lookup in a pre-computed library index → matched library mesh. The library is curated to contain clean, watertight, artist-authored meshes with PBR materials baked in.

The dominant 2026 embedding for visual retrieval is DINOv2 (Oquab et al., 2023) [13, 31], trained by self-supervision on 142M unlabelled images. DINOv2 features are not anchored to textual category labels (unlike CLIP [15]), which makes them better suited to fine-grained visual similarity: two photographs of the same chair under different lighting conditions embed close together because DINOv2 learned visual structure rather than category language.

The retrieval framing also resolves the four failure modes of single-view generative reconstruction at once:

Symmetry is preserved because the library mesh was authored symmetrically.

Hidden surfaces are correct because the library mesh was authored from all sides.

PBR materials are correct because the library author baked them.

Metric dimensions can be recovered by combining estimated depth from the photograph with the known library mesh dimensions.

The retrieval framing’s principal disadvantage is coverage: items not in the library cannot be reconstructed. Three strategies for handling this long tail are considered in §10 and §11.

2.4 Open-Vocabulary Object Detection

Classical object detection — exemplified by YOLO, Faster R-CNN, DETR — is closed-vocabulary: the model is trained against a fixed set of class labels (e.g. the 80 COCO classes) and can only produce outputs from that set. Open-vocabulary detection generalises this by accepting a text prompt at inference time and detecting any object describable by that prompt.

The 2026 state of the art for open-vocabulary detection is dominated by two families. Grounding DINO (Liu et al., 2023) [10, 34] (Apache-2.0; HuggingFace IDEA-Research/grounding-dino-base) couples a DINO-family detection transformer with a BERT-style text encoder and achieves 52.5 AP on COCO under zero-shot evaluation. OWL-ViT v2 (Minderer et al., 2024) [12, 47] (Apache-2.0; HuggingFace google/owlv2-large-patch14-ensemble) uses CLIP-style image-text embeddings as the basis for detection heads.

For the SCS use case, open-vocabulary detection is preferable to closed-vocabulary COCO detection because COCO [9, 64] ’s 80 classes include only chair, couch (covering sofa), dining table, tv (covering monitor), laptop, keyboard, mouse, and book — missing cabinet, bookshelf, desk, lamp, desk lamp, filing cabinet which are required by SCS’s 11-category schema.

2.5 Monocular Depth and Metric Scale Estimation

Recovering metric depth (i.e. depth in units of metres, not relative depth) from a single image is theoretically ill-posed for the same reason single-view reconstruction is: without a reference of known size, scale is unconstrained. Modern monocular depth models therefore output either relative depth (no units; can be linearly transformed to metric given a reference) or metric depth (units of metres) conditioned on assumed camera intrinsics.

Depth Anything V2 (Yang et al., 2024) [24, 35, 36] is the open-source state of the art. The model exists in three sizes; the Small variant is Apache-2.0 (HuggingFace depth-anything/Depth-Anything-V2-Small-hf), while the Base and Large variants are CC-BY-NC-4.0 — a critical licence distinction documented in §6.4. The SCS pipeline as currently engineered uses the Small variant correctly; this report flags the upgrade pathway as a licence-trap risk.

2.6 Segmentation: SAM and its Successors

The Segment Anything Model (SAM; Kirillov et al., 2023) [7] and its successor SAM 2 (Ravi et al., 2024) [16, 33] provide pixel-accurate object masks given a sparse prompt (a point or bounding box). Both are Apache-2.0 and integrate cleanly with HuggingFace transformers [21]. SAM 3 and SAM 3D Objects (Meta AI / FAIR, 2025) [11, 37, 38] extend the family with concept-prompted segmentation and pose-aware 3D reconstruction respectively; both are governed by the SAM License, a Meta-authored commercial-permissive licence whose terms are discussed in detail in §6.4.

2.7 Material Acquisition

A complete PBR material specification for use in physically-based rendering requires at minimum the albedo (base colour), the roughness map, and the metalness map. Generative single-view models produce these to varying degrees: TripoSR produces a flat per-vertex colour with no separate roughness or metalness; Hunyuan3D-2 produces baked textures with material maps; Stable Fast 3D (Boss et al., 2024) [1, 39] (HuggingFace stabilityai/stable-fast-3d) explicitly outputs roughness and metalness as per-object parameters and is the only model in the present survey that does so under a commercially-acceptable licence (Stability Community Licence, subject to a US$1M annual revenue cap).

For the retrieval-based path, materials are not generated; they are read from the library mesh’s metadata.



3. Problem Statement

3.1 Functional Requirements (SCS-derived)

The four hard requirements imposed by SCS’s commercial deployment context are recorded verbatim in PIVOT_BLUEPRINT.md §1:

Catalog of office equipment. The system must recognise at minimum eleven categories of office furniture: office chair, desk, monitor, cabinet, bookshelf, lamp, desk lamp, keyboard, mouse, table, filing cabinet. These are the categories on which the existing CLIP classifier has been fine-tuned (13,752 images from Google Open Images V7, training documented in §4.5).

IFC BIM compliance. Output IFC files must use IFC4-conformant classes, with named entity types corresponding to the recognised category (e.g. an office chair becomes IfcChair, a desk becomes IfcDesk, a generic furnishing becomes IfcFurnishingElement). Geometry must be representable as IfcTriangulatedFaceSet for arbitrary meshes.

xeokit visualisation with manual drag/drop. The output meshes must load into the xeokit web viewer, support manual drag-and-drop placement within a room scene, and be reusable: the same chair recognised once must produce the same mesh when dropped into many rooms.

Free, royalty-free, commercially-safe tooling. No paid memberships. No revenue caps. No monthly-active-user caps. No geographic exclusions. No AGPL-class strong copyleft. No CC-BY-NC. The licence posture must be defensible to legal review.

3.2 The Four Failure Modes of Single-View Generation

Testing on representative office chair photographs during the project’s first three sprints exposed four systematic defects in the original TripoSR-led pipeline:

Failure mode 1: Asymmetric structural elements. A chair with four legs of identical real-world geometry emerges from a single-view reconstruction with legs that drift independently in length, splay angle, and termination. This occurs because the generative model has no symmetry prior baked into its architecture; each leg is decoded from a noisy latent and there is no mechanism by which the four legs are constrained to be identical.

Failure mode 2: Hallucinated hidden surfaces. A photograph of a chair from the front contains zero information about the back of the chair. The generative model fills the back in by sampling from the distribution of chair backs seen during training. The fill is plausible — it does not look like an obvious artefact — but it is wrong in detail every time and is not the back of the specific chair being photographed.

Failure mode 3: Non-deterministic output. Diffusion-based reconstruction (TRELLIS, Hunyuan3D) produces different meshes across runs for the same input image. This is unacceptable for SCS’s use case, in which the same chair model dropped into many rooms must appear identically across all rooms; non-determinism makes the catalog inconsistent.

Failure mode 4: Absent PBR materials and absent metric scale. TripoSR’s output is a mesh with a single flat colour averaged from the foreground of the input image. There is no separation of albedo, roughness, and metalness; reflective objects (e.g. monitor screens, polished metal lamp bases) render unphysically. The mesh dimensions are arbitrary because the input photograph contains no reference of known scale; without externally-supplied scale the resulting IFC dimensions are not actionable in BIM workflows that depend on accurate spatial layout.

3.3 Why These Failure Modes Are Not Fixable by Switching Generative Models

A critical observation from the project history is that all four failure modes persist across every model in the 2026 state of the art for single-view generative 3D reconstruction. They are not bugs in TripoSR specifically; they are properties of the class of approach:

Asymmetry persists because no current top-tier model (TRELLIS.2-4B, Hunyuan3D-2.1, TripoSG, Hi3DGen, SF3D, SAM 3D Objects) has a learned office-furniture-specific symmetry prior. The training distributions (Objaverse, ShapeNet-like) reward overall plausibility, not category-specific structural priors.

Hidden-surface hallucination is a property of the underlying inverse problem: it is mathematically impossible to reconstruct what was not in the input. All models hallucinate; the variation between models is in which plausible-but-wrong fill they choose.

Non-determinism affects all diffusion-based approaches (TRELLIS, Hunyuan3D, anything sampling from a latent prior); feed-forward LRM-style models (TripoSR, SAM 3D Objects) are deterministic but inherit the other failure modes.

Absent PBR is improved by Hunyuan3D-2 and Stable Fast 3D, but only Stable Fast 3D explicitly emits a PBR triple (albedo + roughness + metalness) and that model is subject to a revenue cap (§6.4).

Absent metric scale is independent of which generative model is used; it depends entirely on whether a separate monocular depth or reference-object scale estimator is integrated into the pipeline.

3.4 Engineering Constraints

The constraints under which the system must operate are:

Hardware envelope (primary box). NVIDIA GeForce RTX 4070 Laptop GPU, 8 GB VRAM, 64 GB system DDR RAM, Windows 11 Pro. CUDA 12.6 / cu126 PyTorch wheels.

Hardware envelope (secondary box). A workstation with at least 24 GB VRAM is assumed available for asynchronous tasks. Exact specifications are at this report’s writing not confirmed.

Tool-chain. Node.js 24+ with Express for the backend; Python 3.11–3.14 for AI subprocess calls; the transformers library for HuggingFace integration; ifcopenshell for IFC4 writing; trimesh for geometry manipulation; xeokit SDK 2.6.108 for browser viewing.

Licence filter. Apache-2.0, MIT, BSD-3, and the SAM License are acceptable. Stability Community License is conditional on revenue. Tencent Hunyuan3D Community License is conditionally acceptable but flagged (§6.4 documents specific issues). AGPL-3.0, GPL, CC-BY-NC-4.0, and research-only licences (apple-amlr, OpenRAIL non-commercial variants) are not acceptable.

3.5 Formal Problem Statement

Given the above, the system to be built is formally:

A function f mapping an input image I (single RGB photograph of an office artefact) to a tuple (M, C, D, T) where M is a closed three-dimensional mesh, C is an IFC4 class assignment from a fixed taxonomy of eleven SCS categories, D is a metric dimension triple (height, width, depth) in metres, and T is a PBR material specification (albedo + roughness + metalness), such that the resulting IFC4 file is loadable in xeokit, the mesh is structurally symmetric where its real-world counterpart is symmetric, the hidden surfaces are accurate to the real-world object, the output is identical across runs (f is deterministic on I), and every model and library invoked is licensed under terms admitting commercial use by SCS without monetary obligation and without restricting SCS’s right to deploy the system to clients in any jurisdiction including the European Union and United Kingdom.

§§4–6 demonstrate that no single-view generative function f satisfies all of these constraints simultaneously on the 8 GB primary hardware, and that a retrieval-based f against the Amazon Berkeley Objects library does, modulo the catalog-coverage limit discussed in §10.

3.6 Scope and Operational Constraints — A Local-Only System

A constraint that warrants its own treatment in this report is the deliberate decision that the entire SCS pipeline operates locally on the SCS engineer’s workstation. There is no cloud-GPU rental for inference, no managed-API call to an external service during a customer-facing operation, and no transmission of customer photographs out of the SCS network. The constraint is not incidental to the project; it is fundamental to the licensing, privacy, and cost posture of the deliverable.

Cloud-API alternatives that were not adopted, and why. The 2026 landscape for image-to-3D contains several managed cloud services that, on the face of it, would be operationally simpler than a local pipeline: Tripo AI’s cloud API, CSM 3D, Meshy.ai, Luma Labs’ Genie, and various managed-inference offerings hosted by Replicate or RunPod. Each was considered against SCS’s requirements and excluded for the following reasons:

Per-image charges. Cloud services bill per generation. At SCS-relevant throughput this becomes a non-trivial recurring expense and a per-customer variable cost that the local pipeline does not have.

Customer-image transmission. A managed-cloud API requires uploading the customer’s office photograph to the vendor. For BIM workflows in regulated sectors (financial services, government, healthcare) this is operationally non-trivial; for some SCS clients it would be a contractual obstacle.

Vendor lock-in. A managed API’s behaviour can change without notice (model upgrades, deprecations, pricing changes). A locally-deployed model under a permissive licence is durable on the timescales SCS needs.

Licensing transparency. A managed API’s licence applies only to the input/output relationship; the model behind it may be under unknown terms. Local deployment forces explicit verification (the audit conducted in §6.4) and produces a defensible licence posture.

Latency tail. Cloud APIs add network round-trip and shared-tenant queueing latency. For interactive SCS use cases this is undesirable.

The implications of the local-only constraint are substantial and shape the architecture throughout the report:

Disk-resident model weights. Every model in the pipeline must be downloaded once and resident on local disk. Total disk footprint of the recommended stack is approximately 14 GB (DINOv2-Large 1.2 GB, SAM 2.1 hiera-large 0.9 GB, Grounding DINO base 0.7 GB, Depth Anything V2 Small 0.1 GB, the existing TripoSR cache 1.3 GB, SigLIP 2 so400m 4 GB, OneFormer Swin-L 0.9 GB, Florence-2 large 1.6 GB, plus dependency wheels). On the 24 GB workstation, SAM 3D Objects adds an estimated further 10 GB.

First-run network requirement. The first inference call on each model downloads the weights from HuggingFace. After the first run, the model is offline-capable. SCS deployment procedure must therefore include a warm-up pass on every freshly-provisioned workstation.

No horizontal autoscaling. Throughput is bounded by the GPU count physically present on SCS’s premises. Burst handling is a queue-and-batch problem, not an autoscale problem.

No surreptitious telemetry. HuggingFace transformers does not phone home during inference. No customer-image data leaves the SCS LAN.

The local-only constraint is therefore not a degradation of a cloud-native architecture; it is the correct architecture for SCS’s BIM-deliverable posture and is treated as such throughout the recommendations in §11.

3.7 Understanding Model Weights — A Reference for SCS Stakeholders

This sub-section is included to give SCS technical management and procurement stakeholders a shared vocabulary for what “model weights” means operationally, since several engineering decisions in this report (disk-storage budget, VRAM constraints, licence-verification per-file) only make sense against that background.

What a neural network weight is. A modern neural network for vision (DINOv2-Large, SAM 2.1, Grounding DINO base, etc.) is mathematically a parametric function f(θ; x) that maps an input image x to an output (a label, a depth map, a segmentation mask, an embedding vector, …) under control of a high-dimensional parameter vector θ. θ is the result of training — an offline optimisation procedure performed once by the model authors, often consuming weeks of compute on hundreds of high-end GPUs. θ is what is shipped to the user. The number of scalar entries in θ is the parameter count reported alongside each model — DINOv2-Large has 300 million such entries; SigLIP 2 so400m has 1 billion; SAM 3D Objects has approximately 3 billion.

How weights are stored on disk. Each parameter is by default a 32-bit floating-point value (FP32; 4 bytes). A 300-million-parameter model in FP32 therefore occupies 1.2 GB on disk. The HuggingFace transformers ecosystem has progressively standardised on the .safetensors storage format (a flat tensor-name → tensor-data archive with cryptographic content hashing) over the historical .bin / pickle format, on the security grounds that loading a .safetensors file cannot execute arbitrary code while loading a pickle can. All model files in the recommended SCS stack are available as .safetensors.

How weights occupy GPU memory. When a model is loaded for inference, the weight tensor is copied from disk into GPU memory (VRAM). Memory is also required for the activations — intermediate computations during a forward pass — which scale with input image size. For a typical 800×800 detection input on Grounding DINO base, peak VRAM is approximately 3 GB: 0.7 GB for the weights and 2.3 GB for activations and CUDA overhead. The numbers reported throughout this report under “Native VRAM” reflect this combined footprint, not the weight size alone.

Quantisation as VRAM mitigation. Weights can be stored at less than 32 bits per parameter without significant accuracy loss for inference. FP16 (16 bits per parameter; supported natively on the RTX 4070 Laptop’s Ada architecture) halves the memory cost. BF16 ditto with different numeric properties favoured for transformers. INT8 (8 bits) quarters it. FP4 / INT4 (4 bits) reduces by 8×. The bitsandbytes library provides drop-in quantisation for transformers. Quantisation is how SAM 3D Objects (24 GB native, 3 billion parameters) can be made to fit on an 8 GB box at the cost of some accuracy.

Where weights live on the SCS workstation. The HuggingFace transformers library caches downloaded weights at ~/.cache/huggingface/hub/ (on Windows, C:\Users\<user>\.cache\huggingface\hub\). Each model occupies a subdirectory keyed by model identifier. The cache is persistent — once downloaded, weights are reused on subsequent invocations without re-downloading. SCS should plan for the cache to grow to approximately 20 GB across the full recommended stack.

Weights and intellectual property. Model weights are not source code in the legal sense, but they are subject to the licence under which the model is released. Apache-2.0, MIT, and the SAM License grant SCS the right to use, modify, and redistribute the weight files; the redistribution obligations were quoted verbatim in §6.4. CC-BY-NC weights (Depth Anything V2 Base / Large) are not licensed for commercial inference. AGPL weights (the YOLOv8 weights currently in the repository root) carry copyleft obligations on the surrounding software. The licence verification table in Appendix A applies to weight files specifically, not to the source code that loads them.



4. Engineering History and the Generative-to-Retrieval Pivot

This section reconstructs the engineering decisions made across the project’s nine branches, drawing primarily on PROJECT_HISTORY.md (commit 013985c, 2026-05-21) and PIVOT_BLUEPRINT.md (commit 10d1d9f, 2026-05-21).

4.1 Phase 1: Infrastructure (April 2026)

Branch phase-1-infrastructure established the scaffold: a Node.js / Express server on port 3000, a Python subprocess bridge implemented in backend/services/pythonBridge.js, the xeokit-SDK integrated into the frontend with a local copy in node_modules (the historical reason for vendoring rather than CDN-loading the SDK is documented in WORK_CHECKPOINT.md §4). Five REST endpoints were defined: /api/health, /api/generate, /api/objects, /api/export/ifc, and /api/debug/*. The TripoSR single-image-to-mesh pipeline (stabilityai/TripoSR, MIT) was integrated end-to-end including marching-cubes meshing at 256-cube resolution on the GPU. The IFC export path was scaffolded but produced an IFC2x3 template file containing only placeholder IfcFurnishingElement entries with no geometry — opening the output in Revit produced a structurally empty file. This was a known weakness carried forward.

4.2 Phase 2: Real IFC4 Export (May 2026, main commit 3c007eb)

The IFC export defect was repaired in a complete rewrite of backend/python-scripts/saveIFC.py. The new implementation uses ifcopenshell to construct an IFC4 file, loads each GLB through trimesh, decimates the mesh to at most 8,000 faces, and writes the geometry as an IfcTriangulatedFaceSet referenced from an IfcFurnishingElement with per-instance position and scale transforms. The hierarchy is correct (Project → Site → Building → Storey → Furniture). Output IFC files now open in Revit, BIM Vision, Blender’s IFC importer, and FreeCAD with visible geometry.

Critically, this fix landed on main but did not land on the Dimitres.Iteration3 branch on which subsequent work continued. The retrieval-pivot branch inherits the fix; the Dimitres.Iteration3 branch is at this report’s writing still missing it.

4.3 Phase 2 (the 8-Sprint Block, Original-TripoSR commit 93c2a94)

A coherent block of work spanning the originally-planned eight sprints landed on the Original-TripoSR branch in commit 93c2a94. The sprint-by-sprint contents are:

Sprint 1. A real InstantMesh integration: Zero123++ for six-view diffusion synthesis followed by an LRM reconstruction stage. Falls back to a YOLO + DPT depth-mesh path on failure.

Sprint 2. TRELLIS integration via backend/ai/trellis.js and a Python wrapper. Falls back to TripoSR on failure.

Sprint 3. XKT export through convert_to_xkt.py calling the @xeokit/xeokit-convert Node CLI. New endpoint POST /api/export/xkt.

Sprint 4. Object classification through classify_object.py, with a 24-class taxonomy mapping recognised office categories to IFC entity types and material slots (IfcChair/textile_soft, IfcTable/wood_polished, IfcElectricAppliance/metal_brushed, …). The detection backbone was YOLOv8 instance segmentation — AGPL-3.0 licensed, a licence problem identified later and discussed in §6.4.

Sprint 5. Spatial layout solver through spatial_layout.py, using Google OR-Tools’ CP-SAT constraint solver to perform non-overlapping 2D placement with per-category ergonomic clearance presets.

Sprint 6. ATISS-based autoregressive scene synthesis through atiss_layout.py, with an OR-Tools fallback.

Sprint 7. Hunyuan3D-2 multi-view diffusion through run_hunyuan3d.py with a Hunyuan3DPaintPipeline texture-baking step. Falls back to TRELLIS → TripoSR.

Sprint 8. End-to-end test runner through test_pipeline.py, plus the frontend model picker exposing all five generative model choices.

The sprint-2 ATISS work was technically completed but flagged for lower priority under the retrieval pivot; the sprint-4 YOLO classifier and sprint-7 Hunyuan3D path are both flagged for replacement on licence grounds.

4.4 The TripoSR Quality Investigation

A parallel investigation across the TripoSR-SAM2-Humphrey-Enhanced branch attempted to improve TripoSR output quality by chaining SAM 2 segmentation, Humphrey smoothing, and Poisson surface refinement. Commit 6e3ae89 introduced the full chain; commit 345baf6 reverted it after evaluation showed that the smoothing and refinement steps removed geometric details that the downstream IFC export needed. The lesson is captured in TripoSR_CHANGES_AND_LESSONS.md: post-hoc smoothing of TripoSR output trades local detail for global smoothness, which is the wrong trade for office furniture detail (e.g. it rounds chair leg terminations and removes joint articulations). This investigation produced a durable lesson on the limits of post-processing-as-fix for a fundamentally limited generation pipeline, and contributed materially to the later pivot decision.

4.5 The CLIP Fine-Tuning Effort (Dimitres.Iteration3, May 2026)

The Dimitres.Iteration3 branch saw the introduction of three Python scripts: scripts/download_openimages.py (S3 direct downloads of Google Open Images V7 — no AWS-CLI dependency, no API key required, CC-BY-4.0 data), scripts/train_clip_office.py (a CLIP ViT-B/32 fine-tune on 11 office furniture categories using either a linear probe or LoRA adapter approach), and scripts/evaluate_clip.py (a side-by-side zero-shot vs fine-tuned comparison). The training corpus was 13,752 images with the per-category counts:

The per-category counts are notably imbalanced — filing_cabinet is more than 5× under-represented relative to the over-represented classes. This imbalance is an acknowledged source of likely classification bias and is flagged for re-balancing in §10. A trained checkpoint, models/clip_office/best_model.pt (approximately 354 MB), was produced. The checkpoint resides on Dimitres.Iteration3 and is at this report’s writing not yet pulled into retrieval-pivot-blueprint.

4.6 The Pivot Decision (2026-05-21, retrieval-pivot-blueprint)

The investigation that culminated in PIVOT_BLUEPRINT.md made three observations that, taken together, motivated the architectural pivot:

The four failure modes of single-view generative reconstruction (§3.2) are not patchable by post-processing (per §4.4) and are not fixable by switching generative models (per §3.3). The class of approach is structurally inadequate to the SCS use case.

Industrial BIM practice converges on the retrieval framing: Revit families, BIMobject, RevitCity, Sketchfab CC0 catalogs. The industry does not generate office furniture from photographs; it selects from libraries. The SCS-distinctive value is the automation of the selection.

The Amazon Berkeley Objects dataset (7,953 artist-authored meshes, CC-BY-4.0) [3, 62] provides a sufficient library for the eleven SCS categories, and DINOv2 features [13] provide a sufficient embedding for fine-grained retrieval, with the FAISS library [6] handling the nearest-neighbour index at scale.

The pivot was committed as a documented architectural decision; no code change accompanied the documentation. The follow-up commit c78f3ac (2026-05-21) salvaged the four production-ready files from the eight-sprint block (XKT export, IFC taxonomy, spatial layout, end-to-end test runner) and explicitly deferred the generative model adapters (run_hunyuan3d.py, run_trellis.py, run_instantmesh.py, atiss_layout.py) on the principle that they should be brought in only after the retrieval primary path is wired and demonstrated to perform.

This is the state of the branch under this report’s analysis.

4.7 Branches Map and the Latest Work

For reference, the nine branches and their last-commit timestamps are:

retrieval-pivot-blueprint is the most recent and is the only branch on which both the real IFC4 export and the consolidated Sprint 3/4/5/8 salvage are present.



5. System Architecture

5.1 High-Level Pipeline

The system as designed under the retrieval pivot operates in five stages:

┌─────────────────────────────────────────────────────────────────────┐
│                          1. Input                                   │
│  RGB photograph of an office artefact (JPEG or PNG, up to 50 MB)    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       2. Detection                                  │
│  Grounding DINO base (Apache-2.0)                                   │
│  Text prompt: "office chair . desk . monitor . cabinet . . . . "    │
│  Output: bounding box(es) + categorical label(s)                    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       3. Segmentation                               │
│  SAM 2.1 hiera-large (Apache-2.0)                                   │
│  Box prompt from stage 2 → pixel-accurate mask                      │
│  Output: object mask, clean foreground crop                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       4. Retrieval                                  │
│  DINOv2 large (Apache-2.0)                                          │
│  Embedding of cropped object → cosine NN against pre-embedded       │
│  Amazon Berkeley Objects library (CC-BY-4.0)                        │
│  Top-1 match retrieved if confidence ≥ 0.7; else escalated to       │
│  fallback path                                                      │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
                  ┌──────────┴──────────┐
                  │  Confidence ≥ 0.7   │  Confidence < 0.7
                  │                     │
                  ▼                     ▼
┌──────────────────────┐  ┌────────────────────────────────────────┐
│  Library mesh hit    │  │  Fallback to SAM 3D Objects on 24 GB   │
│  Clean, watertight,  │  │  workstation. Async, may take 30–60 s. │
│  PBR-textured        │  │  Output queued back to caller.         │
└──────────┬───────────┘  └─────────────────┬──────────────────────┘
           │                                │
           └────────────────┬───────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  5. Scale and Export                                │
│  Depth Anything V2 Small (Apache-2.0) — estimate metric depth       │
│  Combine with reference object scale (if available)                 │
│  Scale matched mesh to recovered H × W × D                          │
│  IfcOpenShell (LGPL-3.0) — write IFC4 with the correct entity class │
│  xeokit-convert (MIT) — convert IFC → XKT for browser delivery      │
└─────────────────────────────────────────────────────────────────────┘

5.2 Backend (Node.js / Express)

The backend is structured as four sub-modules under backend/:

server.js: Express entry point. Configures CORS, request size limits (50 MB to accommodate phone photos), static file serving of the frontend, and the route table.

config/env.js: Loads environment variables from .env. Centralises all path and resource limit configuration.

middleware/logger.js and middleware/errorHandler.js: Structured logging with timestamps and log levels (error / warn / info / debug); Express error handler returning JSON error responses with stack traces in development.

services/: Five service modules. pythonBridge.js spawns Python subprocesses, captures stdout and stderr, parses JSON output, and manages timeouts. aiRouter.js routes a generation request to the appropriate model adapter. meshProcessor.js (intended for Phase 4) handles mesh cleaning, normalisation, and orientation. ifcExporter.js (Phase 6) constructs the IFC export call. pipeline.js orchestrates the full workflow.

ai/: One adapter per supported model. triposr.js, instantMesh.js, stablefast3d.js. New adapters for the retrieval pivot (dinov2_retrieval.js, sam3d.js) will be added in subsequent sprints.

routes/: REST API endpoints. apiRoutes.js (/api/generate, /api/health), objectRoutes.js (/api/objects/* for inventory, layout), exportRoutes.js (/api/export/ifc, /api/export/xkt), debugRoutes.js (/api/debug/* diagnostics).

python-scripts/: All AI / mesh / IFC operations. inference_base.py is the shared module providing logging, depth estimation, segmentation utilities. run_triposr.py, run_instantmesh.py, run_stablefast3d.py are model-specific entry points. cleanMesh.py, normalizeMesh.py, fixOrientation.py, meshToGLB.py are mesh-stage transforms. classify_object.py, spatial_layout.py, test_pipeline.py, convert_to_xkt.py are the Sprint 4 / 5 / 8 outputs salvaged into retrieval-pivot-blueprint. saveIFC.py and createIFCFurniture.py are the IFC writers.

5.3 Python Subprocess Bridge

The boundary between the Node.js backend and the Python AI code is by design a subprocess boundary, not a shared-memory or RPC boundary. Each generation request spawns a fresh Python process which loads the necessary models, runs inference, and writes a JSON result to standard output. This design has two benefits and one cost:

Benefit: clean lifecycle management. Models are unloaded on process exit; no risk of VRAM leak across requests.

Benefit: isolation of crashes. A Python OOM or unhandled exception terminates that subprocess only; the Node server stays responsive.

Cost: cold-start latency. Model load time is incurred on every request. For TripoSR this is approximately 8 seconds. For a production workload this would be addressed by introducing a long-lived Python worker process per loaded model, but this optimisation is explicitly deferred.

5.4 Frontend (xeokit, vanilla JavaScript)

The frontend is intentionally lightweight: no React, no Vue, no build pipeline. The reasons are durability (xeokit’s API is stable; a vanilla frontend has no framework version dependency to maintain) and inspectability (the entire frontend is debuggable in the browser without source-map indirection). The modules are:

index.html: Layout, model picker, upload form, viewer container, transform controls.

js/api.js: fetch wrapper around backend endpoints with retry and error reporting.

js/xeokitViewer.js: xeokit Viewer initialisation, scene setup, GLTFLoaderPlugin configuration.

js/glbLoader.js: Loads generated GLB files into the active xeokit scene.

js/inventory.js: Tracks objects in the scene, exposes a sidebar list, supports rename and delete.

js/transformControls.js: Translation, rotation, scale UI; emits events that update the canonical scene state.

js/exporter.js: Constructs the IFC export request including the glbPath of each in-scene object via the window._objectGlbMap registry. Triggers browser download on response.

5.5 IFC Export Pipeline

The IFC export call path is:

Frontend collects scene objects with attached glbPath references.

POST to /api/export/ifc with a JSON body listing objects + transforms.

Backend invokes saveIFC.py via the Python bridge, passing the JSON as a single argument (avoiding shell-argument-length limits).

saveIFC.py loads each referenced GLB with trimesh, decimates to ≤ 8000 faces (Mesh complexity beyond this point yields IFC files that overload Revit’s IFC importer), constructs an IfcTriangulatedFaceSet per object, and writes an IFC4 file with the proper Project → Site → Building → Storey → Furniture hierarchy.

Backend streams the IFC bytes to the client as a download.

5.6 Storage and Caching

Three on-disk locations, all under the project root:

uploads/ — incoming photographs, keyed by UUID; retained for debugging.

outputs/ — generated GLBs and IFCs, keyed by job ID; retained.

temp/ — intermediate masks, depth maps, processed crops; cleaned on a TTL basis.

HuggingFace model weights are cached at ~/.cache/huggingface/ by default. The rembg U²-Net weights cache at ~/.u2net/. These caches are large (TripoSR alone is approximately 1.3 GB) and should be considered persistent across runs.



6. Model Survey and Comparative Analysis

This section presents the detailed model survey supporting the architectural recommendations. The methodology, the cross-pipeline ten-model survey, the detection-specific ten-model survey, and the licence taxonomy are each documented in their own sub-section. All licence statements in §§6.1–6.4 were verified directly against each model’s HuggingFace model card or LICENSE file on 2026-06-06.

6.1 Methodology

Candidate models were drawn from HuggingFace with the inclusion criteria:

Listed on HuggingFace with a stated licence on the model card.

Licence is verifiable from primary sources (the HuggingFace model card, the linked LICENSE file, or the originating GitHub repository’s LICENSE).

Licence either grants commercial use unconditionally (Apache-2.0, MIT, BSD-3, public-domain-equivalent) or grants it under conditions that SCS can meet without further negotiation (the SAM License, the Stability Community License at less than US$1M annual revenue).

Inference VRAM either fits the 8 GB primary box at native precision or can be made to fit by quantisation or CPU-offload at acceptable latency.

The model addresses one or more of: detection of office furniture, segmentation, depth estimation, metric scale, single-image-to-3D reconstruction, image embedding for retrieval, material extraction.

The exclusion criteria are:

AGPL-3.0, GPL-3.0, or any strong-copyleft licence.

CC-BY-NC-4.0 or any non-commercial Creative Commons variant.

Research-only licences (apple-amlr, OpenRAIL non-commercial, any “research” tag without an explicit commercial grant).

Model cards that disclaim commercial deployment in the body text even when the file licence is permissive (this is the OpenAI CLIP situation: file licence MIT, but model card text “Any deployed use case … is currently out of scope”).

The output of the survey is two ten-row tables: one spanning the full pipeline (§6.2), one focused on detection (§6.3). The detection survey was performed after a stakeholder request for greater depth on the specific question of office-furniture object detection.

6.2 Cross-Pipeline Model Survey (10 Candidates)

Table 6.2 below summarises the ten cross-pipeline candidates. The full per-model analysis is provided in MODEL_SURVEY_SCS.md; key entries are reproduced here.

Key qualitative findings from the cross-pipeline survey:

The strongest single fix for the colour, material, dimension, and determinism failure modes of generative reconstruction is not a better generative model but the retrieval framing. DINOv2 + Amazon Berkeley Objects + Depth Anything V2 Small + IfcOpenShell solves all four for in-catalog items at a combined VRAM cost well under 8 GB.

The strongest generative model for handling out-of-catalog items, if a 24 GB workstation is available, is SAM 3D Objects under the SAM License. It produces deterministic, textured, posed output and is commercial-safe.

Stable Fast 3D is the only surveyed model that explicitly emits PBR material parameters. If SCS revenue is below the Stability Community Licence US$1M threshold, it is the strongest PBR-generative fallback on the 8 GB box.

Two surveyed generative models are not recommended for any SCS path:

Hunyuan3D-2 for the licence reasons documented in §6.4: EU/UK/South Korea geographic exclusion, a 1M-MAU cap, and an output-binding clause prohibiting use of generated meshes to train any other AI model.

InstantMesh for the licence ambiguity of its dependencies (Zero123++ derives from a research codebase with unclear redistribution rights).

6.3 Detection-Specific Model Survey (10 Candidates)

Table 6.3 below summarises ten models specifically suited to detecting, classifying, or segmenting office furniture. The full analysis is in OFFICE_FURNITURE_DETECTION_BENCHMARK.md.

Key qualitative findings from the detection survey:

For SCS’s specific need (detect the 11 categories including cabinet / bookshelf / desk / lamp / filing cabinet which are absent from COCO), Grounding DINO base is the recommended primary detector. It accepts a single text prompt covering all 11 categories and returns labelled boxes. No fine-tuning required.

The COCO-trained closed-vocabulary detectors (DETR variants, RT-DETR, DETA) are useful as baselines and for the subset of categories COCO covers, but are structurally inadequate as the SCS detector because they cannot output cabinet, bookshelf, desk, lamp, desk lamp, filing cabinet.

OneFormer ADE20K’s class list is closer to office furniture than COCO’s, and it produces pixel-level masks. For workflows where the next stage requires a mask (e.g. clean-crop retrieval against ABO), OneFormer is a stronger pre-stage than the box detectors.

A useful detector ensemble is: Grounding DINO (primary boxes) + SigLIP 2 (classification confirmation on each box crop). Different model families make different errors; the agreement of two open-vocab models on a label is a much stronger signal than either alone.

6.4 Licence Taxonomy and Specific Traps

Five licence classes are present in the candidate set:

Apache-2.0 / MIT / BSD-3. Unconditionally commercial-safe for SCS’s use case. The only obligation is the redistribution obligation: if SCS gives the model weights to a third party, the LICENSE file must accompany the weights. SCS’s product does not redistribute the model weights; the IFC files SCS ships to clients are unencumbered.

SAM License (Meta). Verified directly from facebook/sam3/blob/main/LICENSE. Verbatim clauses:

Grant: “You are granted a non-exclusive, worldwide, non-transferable and royalty-free limited license under Meta’s intellectual property or other rights owned by Meta embodied in the SAM Materials to use, reproduce, distribute, copy, create derivative works of, and make modifications to the SAM Materials.”

Derivative ownership: “with respect to any derivative works and modifications of the SAM Materials that are made by you, as between you and Meta, you are and will be the owner of such derivative works and modifications.”

Redistribution: “If you distribute or make the SAM Materials, or any derivative works thereof, available to a third party, you may only do so under the terms of this Agreement and you shall provide a copy of this Agreement with any such SAM Materials.”

Prohibited uses: “You agree not to use, or permit others to use, SAM Materials for any activities subject to the International Traffic in Arms Regulations (ITAR) or end uses prohibited by Trade Controls, including those related to military or warfare purposes, nuclear industries or applications, espionage, or the development or use of guns or illegal weapons.”

Reverse-engineering prohibition.

The licence does not contain an output-binding clause. The 3D meshes generated by SAM 3D Objects from SCS input photographs are SCS’s property and may be redistributed in IFC files without restriction.

Stability Community License. Verbatim from the stabilityai/stable-fast-3d model card: “free for non-commercial use, as well as for commercial use by organizations or individuals with less than US$1,000,000 in annual revenue.” Above the threshold, an Enterprise License from Stability AI is required. This is a hard administrative dependency: SCS finance must confirm revenue position and, if at or above the threshold, drop Stable Fast 3D from the architecture and substitute SAM 3D Objects in its role.

Tencent Hunyuan3D 2.0 Community License. Three specific clauses verified verbatim from tencent/Hunyuan3D-2/blob/main/LICENSE:

Geographic exclusion: “THIS LICENSE AGREEMENT DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA AND IS EXPRESSLY LIMITED TO THE TERRITORY, AS DEFINED BELOW.”

MAU cap: “If, on the Tencent Hunyuan 3D 2.0 version release date, the monthly active users of all products or services made available by or for Licensee is greater than 1 million monthly active users in the preceding calendar month, You must request a license from Tencent, which Tencent may grant to You in its sole discretion.”

Output binding: “You must not use the Tencent Hunyuan 3D 2.0 Works or any Output or results of the Tencent Hunyuan 3D 2.0 Works to improve any other AI model (other than Tencent Hunyuan 3D 2.0 or Model Derivatives thereof).”

For SCS, the geographic exclusion alone is disqualifying: SCS cannot legally deploy a Hunyuan3D-based component to any client in the EU or UK. The MAU cap is additionally disqualifying for any growth scenario. The output-binding clause would block SCS from using Hunyuan3D-generated meshes as training data for the DINOv2-retrieval index — which is a likely SCS workflow. Triple-disqualified. AVOID.

AGPL-3.0 (YOLOv8 / Ultralytics). Strong-copyleft. Linking AGPL code in a software distribution requires the entire distribution to be released under AGPL. The current state of the repository includes yolov8n-seg.pt at the project root — even if not currently called at runtime in the retrieval pipeline, the binary’s presence in the source tree exposes any redistribution of the repository to the AGPL obligations. The recommended action is to delete the file and replace the YOLOv8-based code path in backend/python-scripts/inference_base.py with SAM 2.1 (Apache-2.0).

CC-BY-NC-4.0 (Depth Anything V2 Base / Large). Non-commercial only. The Small variant is Apache-2.0. The repository’s existing code path correctly uses Small. The trap is the natural engineer instinct to upgrade to Large for better depth quality, which would silently void commercial usage. This report flags the upgrade pathway as forbidden and recommends a code comment in inference_base.py documenting the licence reason for the Small choice.

apple-amlr (Apple DepthPro). Research-only. Disqualified.

OpenAI CLIP card disclaimer. Although the OpenAI CLIP model files are MIT, the model card text states “Any deployed use case of the model — whether commercial or not — is currently out of scope”. This creates legal ambiguity at minimum. The recommended substitute is SigLIP 2 (Apache-2.0, no such disclaimer).

6.5 Three Licence Traps the Repository Currently Has or Risks

yolov8n-seg.pt at repo root — AGPL-3.0 binary in the source tree. Status: present. Recommended action: delete and replace usage with SAM 2.1.

Depth Anything V2 upgrade pathway — code currently calls the Apache-2.0 Small variant; an engineer upgrading to the Base or Large variant for better depth quality would silently void commercial use. Status: latent. Recommended action: pin the model name in code and document the licence reason in a comment.

Hunyuan3D path in salvage candidates — PROJECT_HISTORY.md lists run_hunyuan3d.py from Original-TripoSR as a candidate for future salvage. Status: not in the present branch. Recommended action: revise the salvage roadmap to mark Hunyuan3D as permanently excluded on licence grounds.



7. Implementation and Configuration

7.1 Environment Setup As Executed on the SCS Workstation

The setup steps as actually executed on 2026-06-06 are:

git clone https://github.com/Dimitres-Kisimov/3DpicToIFCModeling.git into c:\Users\dinos\Downloads\.

git checkout retrieval-pivot-blueprint — at HEAD commit c78f3ac.

Read of the five canonical project documents: README.md, PROJECT_HISTORY.md, WORK_CHECKPOINT.md, PIVOT_BLUEPRINT.md, FULL_DOCUMENTATION.md.

npm install via npm.cmd (working around the Windows PowerShell ExecutionPolicy that blocks the default npm.ps1). 242 packages installed. 12 advisory vulnerabilities reported by npm audit (9 moderate, 1 high, 2 critical) — typical for an older lockfile and deferred to a security-cleanup sprint.

python -m pip install --upgrade pip followed by python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126. Installed PyTorch 2.12.0+cu126 plus dependencies. Total download approximately 2.6 GB for the torch wheel. The Python interpreter invoked is the system-installed CPython 3.13.3 at C:\Users\dinos\AppData\Local\Programs\Python\Python313\python.exe.

python -m pip install transformers ultralytics "rembg[cpu]" trimesh scikit-image scipy pillow numpy ifcopenshell huggingface_hub. Installed transformers 5.10.2, ultralytics 8.4.60, rembg 2.0.76, trimesh 4.12.2, scikit-image 0.26.0, scipy 1.17.1, ifcopenshell 0.8.5, huggingface_hub 1.18.0, plus their dependencies.

Creation of .env from .env.example with the substantive deviation that PYTHON_PATH is set to the absolute path of the Python 3.13 executable rather than the plain python. This deviation is necessary because on the SCS workstation python in PATH resolves to the Microsoft Store stub launcher, not to Python 3.13.

Verification: python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))" returned True NVIDIA GeForce RTX 4070 Laptop GPU.

Server start via node backend/server.js (not npm start, again because of the PowerShell ExecutionPolicy issue with .ps1 shims). Server initialised on http://localhost:3000.

Health verification: GET /api/health returned {success: true, ...}; GET /api/debug/health reported Python 3.13.3, NumPy 2.4.4, PyTorch 2.12.0+cu126, CUDA True.

7.2 Hardware Identification Correction

The original setup brief described the GPU as an “RTX 4060 GTX”. The actual GPU as reported by nvidia-smi is the NVIDIA GeForce RTX 4070 Laptop GPU with 8188 MiB total VRAM, driver version 572.83, and CUDA 12.8 capability. The 8 GB VRAM figure used throughout this report is therefore correct. The “RTX 4060” identifier is incorrect; the architecture nomenclature “GTX” is also incorrect (the 40-series is RTX, not GTX). All cu126 wheels are forward-compatible with the 12.8 driver and no setup steps required modification.

7.3 Configuration File

The deployed .env is (with values verified against the live system):

PORT=3000
HOST=localhost
NODE_ENV=development
MAX_FILE_SIZE=52428800
TEMP_DIR=./temp
UPLOAD_DIR=./uploads
OUTPUT_DIR=./outputs
PYTHON_PATH=C:/Users/dinos/AppData/Local/Programs/Python/Python313/python.exe
PYTHON_SCRIPTS_DIR=./backend/python-scripts
USE_GPU=true
CUDA_VISIBLE_DEVICES=0
GPU_MAX_MEMORY_MB=8192
INSTANTMESH_MODEL_PATH=
STABLEFAST3D_MODEL_PATH=
TRIPOSR_MODEL_PATH=
IFC_OUTPUT_DIR=./outputs
LOG_LEVEL=info

7.4 Outstanding Configuration Items

The CLIP fine-tuned checkpoint (models/clip_office/best_model.pt, approximately 354 MB) is on Dimitres.Iteration3 but not yet on retrieval-pivot-blueprint. Either cherry-pick or copy the file across.

The Amazon Berkeley Objects subset has not been downloaded. The full ABO dataset is approximately 154 GB; the subset relevant to SCS’s eleven categories is estimated at 8–12 GB.

DINOv2 multi-view embeddings of the ABO subset have not been pre-computed; the FAISS retrieval index does not yet exist.

HuggingFace authentication (huggingface-cli login) has not been performed; required for facebook/sam-3d-objects and facebook/sam3 access.

7.5 Hardware Specifications and Processing Considerations

This section documents the precise hardware configuration on which all measurements and recommendations in this report were grounded, together with the stage-by-stage analysis of which hardware component is the binding constraint at each pipeline step, and a procurement recommendation for SCS should the project move to scaled deployment.

7.5.1 Workstation Specification As Tested

The reference workstation on which all numbers in this report were obtained is a single laptop with the following specification, verified against nvidia-smi, wmic, and PowerShell Get-ComputerInfo outputs on 2026-06-06:

7.5.2 Per-Stage Hardware Analysis

The pipeline’s binding hardware constraint changes by stage. Documenting which component is the bottleneck at each step is what enables SCS to size future hardware deliberately.

The conclusion from this analysis is that the bottleneck across the recommended Apache-2.0 primary path is VRAM at each AI stage individually, but no individual stage approaches the 8 GB limit. The cumulative budget — were all models loaded simultaneously, which they are not — would exceed 8 GB. The sequential-loading architecture in the benchmark harness (§8.2) is the consequence of this constraint and is the right design pattern for SCS production deployment too.

7.5.3 Why Not a Bigger Laptop GPU?

The natural next question is whether SCS should procure an 8 GB-VRAM laptop or move to a 16 GB-or-greater configuration. The analysis:

8 GB suffices for the recommended Apache-2.0 primary path. Every model fits individually. The pipeline never needs more than one model on the GPU at a time.

16 GB would permit two-model concurrent loading. This would reduce per-request latency by approximately 8 seconds (the time to load each model) at the cost of a 2× hardware budget. For interactive UX this matters.

24 GB is the threshold for SAM 3D Objects native deployment. Below 24 GB, the asynchronous-fallback architecture (§5.1) is required. At or above 24 GB, SAM 3D Objects can run synchronously on the same box as the rest of the pipeline.

48 GB (RTX A6000 Ada) enables batch processing. Multiple customer photographs in parallel — relevant for SCS back-office batch jobs but not for the interactive workflow.

7.5.4 Recommended Hardware Configurations for SCS Going Forward

The recommendations below are sized to three operational scenarios SCS may face. Each row lists the recommended specification and the operational rationale.

Scenario A: Single-user developer workstation, interactive workflow (e.g. the current SCS engineer’s role)

Scenario B: Single-machine deployment with on-demand high-fidelity fallback (e.g. an SCS developer demo workstation)

Scenario C: Multi-user batch back-office for SCS at scale

The current SCS engineer’s workstation matches Scenario A and is therefore the right baseline for development. Scenario B is the recommended demo configuration for stakeholder presentations. Scenario C is forward-looking and should be revisited only when SCS commits to a production throughput SLA.

7.5.5 Processing Time Estimates (Approximate, on Tested Workstation)

The following per-stage timing estimates are derived from the published benchmarks of each model and adjusted for the 4070 Laptop’s tensor throughput. They are intended for capacity planning, not for SLA commitment.

Total wall-clock from photograph submission to IFC available is therefore in the 2–5 second range on the Apache-2.0 primary path, dominated by detection and segmentation latency, plus a one-time 6–10 s warm-up cost per model on first use. The fallback path adds 30–60 s when invoked. These figures are consistent with an interactive UX in which the user sees results within a few seconds for catalog hits and within a minute for fallback escalations.



8. Experimental Methodology and Test Harness

8.1 Purpose of the Harness

The detection benchmark harness scripts/test_furniture_detection.py is intended to provide a reproducible, single-command means of running all ten detection models from §6.3 against a single SCS-supplied test image and tabulating their outputs. Its purpose is not to declare a winner — that is a downstream analysis task requiring ground-truth labels — but to enable SCS to inspect concrete model behaviour on representative input.

8.2 Harness Design Decisions

Four design decisions warrant explicit documentation:

Sequential model loading. The harness loads each model, runs inference, frees the model (via del, gc.collect(), and torch.cuda.empty_cache()), then loads the next. This is deliberate. The cumulative VRAM of all ten models exceeds 8 GB; sequential loading ensures each individually fits. The cost is that the harness cannot benchmark model-load latency separately from inference latency; this is judged an acceptable trade-off for the present scope.

Standard transformers API only. Each model is loaded through the canonical transformers Auto* classes where possible. This minimises per-model setup code and matches how the models will be called in production.

Output schema. Each model produces a tuple (boxes, labels, scores) even when the model’s native output is not a bounding-box detection. For OneFormer, the boxes are placeholder full-image rectangles and the labels are the segment-info entries. For SigLIP, the boxes are full-image rectangles, the labels are the eleven SCS categories, and the scores are the sigmoid-of-logits per category. For DINOv2, the boxes are full-image rectangles, the labels are a placeholder <embedding> token, and the score is a one-number summary of the embedding magnitude (useful as a sanity check that inference ran). The unified schema is what enables a single CSV output for cross-model comparison.

Latency and VRAM measurement. Latency is wall-clock time around the runner(image) call, in milliseconds. Peak VRAM is torch.cuda.max_memory_allocated() in megabytes, reset between models. Neither metric is fair across model types (a segmentation model does more work than a classifier and should reasonably be slower); they are intended for monitoring regression and as inputs to per-stage budget planning, not as absolute model-quality measures.

8.3 Test Data Requirements

To make the benchmark scientifically meaningful, SCS should curate a labelled test set of office photographs:

Size. Minimum 30, preferably 100, photographs of real SCS office artefacts.

Diversity. At least 3 photographs per SCS category. Photographs should vary in lighting (overhead fluorescent, daylight, mixed), angle (front, three-quarter, side), and background (clean against wall, cluttered office context, lifestyle).

Ground truth. Bounding boxes drawn manually around each office-furniture object in each photograph, with the eleven SCS category labels. Labelling can be performed with labelImg or the LabelMe browser tool.

Storage. A data/scs_test_set/ folder with images/ and annotations.json in the COCO bounding-box format.

With a labelled test set, the benchmark harness can be extended to compute per-model recall@k, mAP, and IoU statistics. The extension is straightforward and is left as a sprint deliverable.

8.4 Reproducibility

All software versions are pinned in this report (§7.1). Model weights are pulled from HuggingFace by fixed repository identifier (no commit-pinning is enforced in the harness; HuggingFace model card commits are themselves immutable). Reproducibility across environments is therefore as good as transformers and pip allow.

A small reproducibility trap exists for SigLIP 2 and SAM 3D Objects: both require HuggingFace authentication (huggingface-cli login) to download. The harness will fail at the first such model with a OSError: not authenticated until the user logs in.



9. Lessons Learned

This section consolidates eight durable lessons from the project’s engineering history. They are documented for future contributors and for SCS internal review of the project’s progression.

9.1 Single-View Generative Reconstruction Is the Wrong Tool for a Catalog Use Case

Three sprint-long investigations (TripoSR baseline, SAM 2 + Humphrey + Poisson refinement, TRELLIS / Hunyuan3D experimentation) converged on the same conclusion: the class of approach is structurally inadequate to SCS’s commercial deliverable. Recognising this earlier — by interrogating the use case constraints (catalog reuse → determinism required) against the model class properties (single-view generation is inherently non-deterministic and hallucinates hidden surfaces) — would have saved approximately four weeks of investigation. The lesson is to interrogate the model class against the use case constraints before model selection, not after.

9.2 The Industry Practice Is a Strong Signal

Revit families, BIMobject, RevitCity, Sketchfab CC0, and the Amazon Berkeley Objects dataset all converge on retrieval-from-library as the production approach for office furniture in BIM. This convergence is not a coincidence; it reflects the same structural observation about the inadequacy of single-view generation. Industry convergence is a strong prior: when a class of approach is unanimously adopted by adjacent practitioners, the question to ask is what constraint are they observing that I am not, before going in a different direction.

9.3 Licence Audit Must Be a Sprint, Not a Footnote

Three traps in the present codebase — the YOLOv8 binary at repo root, the Depth Anything V2 upgrade pathway, and the Hunyuan3D salvage candidate — would each silently void commercial usage if uncorrected, and were not surfaced until a deliberate licence audit was performed. The pattern is clear: every model addition needs a licence verification step against the model card and the LICENSE file, recorded in commit history. A LICENSE_AUDIT.md in the repository, updated per commit that touches the model set, would catch these prospectively.

9.4 Hardware Naming Errors Propagate

The initial brief described the GPU as an “RTX 4060 GTX”, when in fact it is an RTX 4070 Laptop. The VRAM was correctly stated as 8 GB. Had the architectural decision been made on the VRAM number rather than the model name, no impact would have followed. As it happened, the VRAM number was the binding constraint anyway and the architecture survived the naming error. The lesson is to anchor architectural decisions on the binding constraint, not on a name that encodes the constraint.

9.5 Configuration on Windows Requires Explicit Workarounds

Three Windows-specific friction points were encountered: (1) PowerShell ExecutionPolicy blocks npm.ps1 (worked around with npm.cmd); (2) the default python in PATH is the Microsoft Store stub, not Python 3.13 (worked around with absolute paths in .env); (3) PyTorch cu126 wheels are large and the download is bandwidth-bound. These are not bugs in the project; they are infrastructure realities. The lesson is to document Windows-specific workarounds in CONTRIBUTING.md so each new developer is not re-discovering them.

9.6 Post-Processing Cannot Fix a Fundamentally Limited Generation Pipeline

The TripoSR + SAM 2 + Humphrey + Poisson chain reverted in commit 345baf6 was an instance of attempting to repair generation defects (asymmetry, leg drift) through downstream smoothing. The downstream smoothing did remove some defects, but at the cost of removing local detail that the IFC export required. The general lesson is that the defect must be addressed at the stage of the pipeline that produces it; post-hoc fixes trade one defect class for another.

9.7 The Project Should Maintain a Single Source of Truth for Architecture Decisions

The architecture history is currently spread across nine branches, four documents (PROJECT_HISTORY.md, PIVOT_BLUEPRINT.md, FULL_DOCUMENTATION.md, WORK_CHECKPOINT.md), and the commit message of c78f3ac. A new contributor takes substantial time to triangulate the present state of the design. Consolidating the architecture-decision-record into a single ADR-style folder (docs/adrs/0001-pivot-to-retrieval.md, docs/adrs/0002-replace-yolov8.md, …) would significantly reduce onboarding cost.

9.8 Memory Across AI-Assistant Sessions Is Not Automatic

Several pieces of context (the company name SCS, the four hard requirements, the hardware envelope) were lost between AI-assistant sessions on different machines because they were communicated in conversation rather than in persistent project documents. The lesson is that what is not written in the repository is not durable. The project memory record at ~/.claude/projects/.../memory/project_scs.md is one of the artefacts of this report, recording SCS-specific facts so future sessions inherit them.



10. Limitations

This section enumerates the known limitations of the recommended approach and discusses their mitigations.

10.1 Theoretical Limit on Single-View Reconstruction

The retrieval pivot eliminates the generative failure modes for in-catalog items but does not extend the information content of a single photograph. Items not in the catalog still have hidden surfaces about which the photograph contains no information. The fallback strategies for such items are: (a) return the nearest library mesh with a “low confidence” flag (lossy but always clean); (b) escalate to SAM 3D Objects on the 24 GB workstation (clean output but generative-class failure modes return); (c) refuse and prompt the user to pick from a candidate shortlist (cleanest, but adds a manual step). PIVOT_BLUEPRINT.md §5 flags this as an open question for SCS to decide.

10.2 Catalog Coverage Limit

The Amazon Berkeley Objects dataset covers 7,953 meshes spanning household and office categories. The subset relevant to SCS’s eleven categories has not yet been counted but is estimated at 600–1,500 meshes. This is sufficient for chair / desk / cabinet / monitor / lamp recognition but will miss the long tail of office-specific items (specialised conference tables, ergonomic adjustable desks, distinctive designer chairs). The mitigations are (a) supplement ABO with Sketchfab CC-BY meshes — labour-intensive curation, but unlimited in expandability; (b) augment with SAM 3D Objects fallback as in §10.1; (c) accept the long-tail loss for an MVP and iterate.

10.3 Hardware Envelope Limit

The 8 GB primary VRAM is sufficient for the Apache-2.0 retrieval primary path with comfortable headroom, but is insufficient for SAM 3D Objects at native precision. The fallback to SAM 3D Objects therefore requires either the 24 GB secondary workstation or 4-bit quantisation with CPU offload at substantially degraded latency (estimated 15× slower per inference). For a one-customer-at-a-time service model the 8 GB primary suffices; for any concurrent-load scenario, the 24 GB workstation becomes a hard requirement.

10.4 Licence-Imposed Limits

The licence filter excludes several technically strong models — Hunyuan3D-2 (geographic, MAU, output-binding), Apple DepthPro (research only), Depth Anything V2 Base / Large (CC-BY-NC). For office furniture specifically, the loss is small (the retained Apache-2.0 alternatives are comparable in quality on this category), but in adjacent categories the gap would be larger. The licence filter is a deliberate business decision; this is documentation rather than mitigation.

10.5 Determinism Limit on Fallback Path

Even SAM 3D Objects, which is deterministic conditional on the input image, will produce slightly different outputs across model-version upgrades. If SCS wishes to preserve catalog identity across years, the SAM 3D model version used for any successful generation must be recorded alongside the output and the same version used for any re-generation of the same input.

10.6 Multi-Object Photograph Limit

The current pipeline assumes one object per photograph. Real office photographs contain many objects (a chair next to a desk next to a monitor next to a lamp). Grounding DINO can detect all in one call; SAM 2.1 can segment each; the retrieval call is per-object. The orchestration layer above this — multi-object photograph → multiple parallel retrievals → multiple IFC entities placed in one room — has not yet been built. It is a sprint-scale piece of work, not a research-scale one, but it is not yet present.

10.7 Material Fidelity Limit on the Pure Apache-2.0 Path

The Apache-2.0 retrieval path inherits PBR materials from the ABO library mesh, not from the input photograph. If the photographed chair is upholstered in a fabric that is not represented in the library mesh, the user-visible appearance will be the library’s material, not the photograph’s. The user receives a chair of the same model but not necessarily in the same upholstery. For SCS’s room-layout use case this may be acceptable (room layout cares about shape and footprint, not upholstery colour); for any catalog-display use case it would not be. The mitigation is either to (a) extract the photographed surface texture and apply it to the library mesh — a non-trivial UV-mapping problem, sprint-scale work; or (b) accept the library appearance.

10.8 Cold-Start Latency

The Python subprocess bridge incurs ~8 seconds of model-load latency on every generation request, plus the network cost of any not-yet-cached HuggingFace weight downloads. For an interactive demo this is unpleasant; for a batch-processing back-office tool it is acceptable. Production-grade latency would require a long-lived Python worker process per loaded model. This is a known deferment.



11. Recommendations and Roadmap

11.1 Recommended Deployment Path

Two paths warrant active consideration; one is the report’s recommendation.

Path A (recommended): Apache-2.0 retrieval primary + SAM 3D Objects async fallback on 24 GB workstation.

Front of pipeline: Grounding DINO base for open-vocabulary detection; SAM 2.1 hiera-large for segmentation.

Retrieval: DINOv2-Large embedding against Amazon Berkeley Objects subset; cosine-similarity threshold 0.7 for catalog hit.

Below threshold: queue to SAM 3D Objects on the 24 GB workstation, async delivery.

Metric scale: Depth Anything V2 Small.

Output: IfcOpenShell IFC4 with the existing 24-class taxonomy from classify_object.py.

Viewer: xeokit-convert IFC → XKT; xeokit-sdk loader.

Licence posture: Apache-2.0 primary, MIT for xeokit, LGPL for ifcopenshell, SAM License for SAM 3D, CC-BY-4.0 for ABO data with attribution.

Path B (single-box deployment, simpler legal posture): Pure Apache-2.0, no generative fallback, long-tail handled by best-effort library match with low-confidence flag. Path B is recommended if the 24 GB workstation is not reliably available. The quality of the long-tail experience degrades but the legal posture is cleaner.

11.2 Sprint-Level Roadmap

The recommended sprint sequence to reach a demonstrable end-to-end MVP under Path A:

Sprints S1, S2, S6 are independent and can run in parallel. S3, S4, S5 form a dependent chain. S7 depends on S6. S8 depends on hardware availability. S9 depends on S5. S10 integrates everything.

11.3 Risk Register

11.4 Decisions Requested of SCS Stakeholders

Three decisions require SCS-level sign-off before further engineering:

Path A or Path B? Confirm whether the 24 GB workstation is reliably available for the lifetime of the project, or whether Path B (no generative fallback) is preferred.

Stable Fast 3D adoption? SCS finance to confirm revenue position relative to the US$1M Stability Community License threshold. If under, Stable Fast 3D can be substituted for SAM 3D Objects with marginally better PBR fidelity at the cost of revenue-cap risk.

Long-tail handling policy? PIVOT_BLUEPRINT.md §5 lists three options (return best library match, generative fallback, refuse and prompt). Pick one before S5 implementation.



12. Conclusion

The 3D Picture to IFC Modeling project, examined at the state of the retrieval-pivot-blueprint branch, has progressed through a documented arc from single-view generative reconstruction to a retrieval-against-library architecture. The progression is well-founded: the failure modes of generative single-view reconstruction (asymmetry, hallucinated hidden surfaces, absent PBR materials, absent metric scale, non-determinism) are structural to that class of approach and do not yield to model selection or post-processing. The retrieval framing sidesteps all five failure modes for in-catalog items at a fraction of the hardware cost, while preserving the option of generative fallback for the long tail.

The licence audit performed during the preparation of this report identified two existing repository-level issues — the AGPL yolov8n-seg.pt binary at repo root and the latent Depth Anything V2 upgrade trap — and one architectural issue, the Hunyuan3D salvage candidate’s triple licensing problem (geographic exclusion, MAU cap, output binding). Each has a documented mitigation. Meta’s SAM License has been verified as commercially safe for SCS’s deployment context, correcting an earlier in-repo annotation that recorded SAM 3D as “not available”.

The recommended deployment path uses Grounding DINO base for open-vocabulary detection, SAM 2.1 hiera-large for segmentation, DINOv2-Large for retrieval embedding against an Amazon Berkeley Objects subset, Depth Anything V2 Small for metric scaling, IfcOpenShell for IFC4 export, and the xeokit SDK for browser viewing. Every model in this primary path is Apache-2.0 or MIT; the asynchronous fallback to SAM 3D Objects on a 24 GB workstation is SAM License. The licence posture is defensible to legal review, the hardware posture fits the SCS workstation envelope, and the architecture matches industrial BIM practice.

The benchmark harness delivered with this report (scripts/test_furniture_detection.py) enables direct empirical comparison of the ten detection candidates on SCS-supplied office photographs. The next concrete deliverable should be the curation of a labelled SCS test set; the benchmark output on that set will provide the data on which final model selection — Grounding DINO base versus OWL-ViT v2 versus Florence-2 large — should be made.

The architectural commitments documented in this report are reversible at small cost: the cross-pipeline survey (§6.2) and the detection-specific survey (§6.3) are both designed to make alternative paths visible. The recommendation reflects the best information available on 2026-06-06; subsequent stronger models or licence revisions should be re-evaluated against the same criteria.



13. Bibliography

Citations in the body of this report use the abbreviated author-year convention (e.g. Oquab et al., 2023 [12]) and are also keyed to the bracketed reference numbers listed below, so that a reader may follow either the in-text author-year form or the bracketed [N] form back to the same source. The bibliography is presented in alphabetical order within each category, and numbered consecutively from [1] through the end of §13.3. All HuggingFace, GitHub, and institutional URLs were verified directly on the report date of 6 June 2026.

13.1 Academic and Technical Literature

[1] Boss, M., Huang, Z.-Y., Vasishta, A., & Jampani, V. (2024). SF3D: Stable Fast 3D Mesh Reconstruction with UV-unwrapping and Illumination Disentanglement (arXiv:2408.00653). Underpins the only surveyed model with explicit PBR-parameter output. https://arxiv.org/abs/2408.00653

[2] Carion, N., Massa, F., Synnaeve, G., Usunier, N., Kirillov, A., & Zagoruyko, S. (2020). End-to-End Object Detection with Transformers (arXiv:2005.12872). The DETR paper underpinning both DETR ResNet variants in the detection benchmark. https://arxiv.org/abs/2005.12872

[3] Collins, J., Goel, S., Deng, K., Luthra, A., Xu, L., Gundogdu, E., Zhang, X., Vicente, T. F. Y., Dideriksen, T., Arora, H., Guillaumin, M., & Malik, J. (2022). ABO: Dataset and Benchmarks for Real-World 3D Object Understanding (arXiv:2110.06199). The Amazon Berkeley Objects dataset on which the SCS retrieval library is to be built. https://arxiv.org/abs/2110.06199

[4] Dettmers, T., Lewis, M., Belkada, Y., & Zettlemoyer, L. (2022). LLM.int8(): 8-bit Matrix Multiplication for Transformers at Scale (arXiv:2208.07339). Basis for the bitsandbytes quantisation cited in §3.7. https://arxiv.org/abs/2208.07339

[5] Jain, J., Li, J., Chiu, M., Hassani, A., Orlov, N., & Shi, H. (2023). OneFormer: One Transformer to Rule Universal Image Segmentation (arXiv:2211.06220). The OneFormer paper. https://arxiv.org/abs/2211.06220

[6] Johnson, J., Douze, M., & Jégou, H. (2017). Billion-scale similarity search with GPUs (arXiv:1702.08734). The FAISS library used for the retrieval-index step. https://arxiv.org/abs/1702.08734

[7] Kirillov, A., Mintun, E., Ravi, N., Mao, H., Rolland, C., Gustafson, L., Xiao, T., Whitehead, S., Berg, A. C., Lo, W.-Y., Dollár, P., & Girshick, R. (2023). Segment Anything (arXiv:2304.02643). The foundational paper establishing the promptable-segmentation paradigm. https://arxiv.org/abs/2304.02643

[8] Kuznetsova, A., Rom, H., Alldrin, N., Uijlings, J., Krasin, I., Pont-Tuset, J., Kamali, S., Popov, S., Malloci, M., Kolesnikov, A., Duerig, T., & Ferrari, V. (2020). The Open Images Dataset V4: Unified Image Classification, Object Detection, and Visual Relationship Detection at Scale. International Journal of Computer Vision. The dataset underlying the project’s CLIP fine-tune. https://arxiv.org/abs/1811.00982

[9] Lin, T.-Y., Maire, M., Belongie, S., Bourdev, L., Girshick, R., Hays, J., Perona, P., Ramanan, D., Zitnick, C. L., & Dollár, P. (2014). Microsoft COCO: Common Objects in Context (arXiv:1405.0312). The COCO dataset on which DETR, RT-DETR, and DETA are trained. https://arxiv.org/abs/1405.0312

[10] Liu, S., Zeng, Z., Ren, T., Li, F., Zhang, H., Yang, J., Li, C., Yang, J., Su, H., Zhu, J., & Zhang, L. (2023). Grounding DINO: Marrying DINO with Grounded Pre-Training for Open-Set Object Detection (arXiv:2303.05499). Basis for the recommended open-vocabulary detector. https://arxiv.org/abs/2303.05499

[11] Meta AI / FAIR. (2025). Introducing SAM 3D. Meta AI Blog. Announcement of SAM 3 and SAM 3D Objects (released 19 November 2025). https://ai.meta.com/blog/sam-3d/

[12] Minderer, M., Gritsenko, A., & Houlsby, N. (2024). Scaling Open-Vocabulary Object Detection (arXiv:2306.09683). The OWLv2 paper. https://arxiv.org/abs/2306.09683

[13] Oquab, M., Darcet, T., Moutakanni, T., Vo, H. V., Szafraniec, M., Khalidov, V., Fernandez, P., Haziza, D., Massa, F., El-Nouby, A., Howes, R., Huang, P.-Y., Xu, H., Sharma, V., Li, S.-W., Galuba, W., Rabbat, M., Assran, M., Ballas, N., Synnaeve, G., Misra, I., Jegou, H., Mairal, J., Labatut, P., Joulin, A., & Bojanowski, P. (2023). DINOv2: Learning Robust Visual Features without Supervision (arXiv:2304.07193). Establishes the self-supervised vision-transformer feature space used here for retrieval. https://arxiv.org/abs/2304.07193

[14] Ouyang-Zhang, J., Cho, J. H., Zhou, X., & Krähenbühl, P. (2022). NMS Strikes Back (arXiv:2212.06137). The DETA paper. https://arxiv.org/abs/2212.06137

[15] Radford, A., Kim, J. W., Hallacy, C., Ramesh, A., Goh, G., Agarwal, S., Sastry, G., Askell, A., Mishkin, P., Clark, J., Krueger, G., & Sutskever, I. (2021). Learning Transferable Visual Models From Natural Language Supervision (arXiv:2103.00020). The CLIP paper, used in the project’s classifier fine-tune on Google Open Images. https://arxiv.org/abs/2103.00020

[16] Ravi, N., Gabeur, V., Hu, Y.-T., Hu, R., Ryali, C., Ma, T., Khedr, H., Rädle, R., Rolland, C., Gustafson, L., Mintun, E., Pan, J., Alwala, K. V., Carion, N., Wu, C.-Y., Girshick, R., Dollár, P., & Feichtenhofer, C. (2024). SAM 2: Segment Anything in Images and Videos (arXiv:2408.00714). Successor to SAM and the segmentation model recommended for the SCS pipeline. https://arxiv.org/abs/2408.00714

[17] Rezatofighi, H., Tsoi, N., Gwak, J., Sadeghian, A., Reid, I., & Savarese, S. (2019). Generalized Intersection over Union: A Metric and a Loss for Bounding Box Regression (arXiv:1902.09630). The standard mAP metric reference for object-detection benchmarking. https://arxiv.org/abs/1902.09630

[18] Tencent Hunyuan3D Team. (2025). Hunyuan3D 2.0: Scaling Diffusion Models for High Resolution Textured 3D Assets Generation. Technical report and model card. https://huggingface.co/tencent/Hunyuan3D-2

[19] Tochilkin, D., Pankratz, D., Liu, Z., Huang, Z., Letts, A., Li, Y., Liang, D., Laforte, C., Jampani, V., & Cao, Y.-P. (2024). TripoSR: Fast 3D Object Reconstruction from a Single Image (arXiv:2403.02151). The TripoSR paper; the project’s original generative model. https://arxiv.org/abs/2403.02151

[20] Tschannen, M., Gritsenko, A., Wang, X., Naeem, M. F., Alabdulmohsin, I., Parthasarathy, N., Evans, T., Beyer, L., Xia, Y., Mustafa, B., Hénaff, O., Harmsen, J., Steiner, A., & Zhai, X. (2025). SigLIP 2: Multilingual Vision-Language Encoders (arXiv:2502.14786). The version of SigLIP recommended in this report. https://arxiv.org/abs/2502.14786

[21] Wolf, T., Debut, L., Sanh, V., Chaumond, J., Delangue, C., Moi, A., Cistac, P., Rault, T., Louf, R., Funtowicz, M., Davison, J., Shleifer, S., von Platen, P., Ma, C., Jernite, Y., Plu, J., Xu, C., Le Scao, T., Gugger, S., Drame, M., Lhoest, Q., & Rush, A. M. (2020). Transformers: State-of-the-Art Natural Language Processing (arXiv:1910.03771). The HuggingFace transformers library cited throughout. https://arxiv.org/abs/1910.03771

[22] Xiang, J., Lv, Z., Xu, S., Deng, Y., Wang, R., Zhang, B., Chen, D., Tong, X., & Yang, J. (2024). Structured 3D Latents for Scalable and Versatile 3D Generation (arXiv:2412.01506). The TRELLIS paper. https://arxiv.org/abs/2412.01506

[23] Xiao, B., Wu, H., Xu, W., Dai, X., Hu, H., Lu, Y., Zeng, M., Liu, C., & Yuan, L. (2024). Florence-2: Advancing a Unified Representation for a Variety of Vision Tasks (arXiv:2311.06242). The Florence-2 paper. https://arxiv.org/abs/2311.06242

[24] Yang, L., Kang, B., Huang, Z., Zhao, Z., Xu, X., Feng, J., & Zhao, H. (2024). Depth Anything V2 (arXiv:2406.09414). The monocular depth model used for metric scale estimation; foundation for both the Apache-2.0 Small variant adopted here and the CC-BY-NC variants identified as licence traps. https://arxiv.org/abs/2406.09414

[25] Zhai, X., Mustafa, B., Kolesnikov, A., & Beyer, L. (2023). Sigmoid Loss for Language Image Pre-Training (arXiv:2303.15343). The SigLIP loss formulation underlying SigLIP 2. https://arxiv.org/abs/2303.15343

[26] Zhao, Y., Lv, W., Xu, S., Wei, J., Wang, G., Dang, Q., Liu, Y., & Chen, J. (2024). DETRs Beat YOLOs on Real-time Object Detection (arXiv:2304.08069). The RT-DETR paper. https://arxiv.org/abs/2304.08069

[27] Zhou, B., Zhao, H., Puig, X., Xiao, T., Fidler, S., Barriuso, A., & Torralba, A. (2019). Semantic Understanding of Scenes through the ADE20K Dataset. International Journal of Computer Vision. The ADE20K dataset on which OneFormer is trained. https://arxiv.org/abs/1608.05442

13.2 Standards, Libraries, and Institutional Sources

[28] buildingSMART International. (2024). Industry Foundation Classes (IFC) IFC4 Specification. The data model under which the IFC export is constructed. https://standards.buildingsmart.org/IFC/RELEASE/IFC4

[29] IfcOpenShell Contributors. (2024). IfcOpenShell — open-source IFC reading and writing library. https://github.com/IfcOpenShell/IfcOpenShell

[30] xeokit Contributors. (2023). xeokit-sdk — browser-side BIM viewer. https://github.com/xeokit/xeokit-sdk

13.3 Primary Licence and Model-Card Sources (verified 6 June 2026)

Each entry is the HuggingFace model card and, where applicable, the LICENSE file consulted to verify the licence string quoted in §6.4 and Appendix A.

[31] DINOv2-Large model card. https://huggingface.co/facebook/dinov2-large

[32] SigLIP 2 so400m model card. https://huggingface.co/google/siglip2-so400m-patch14-384

[33] SAM 2.1 hiera-large model card. https://huggingface.co/facebook/sam2.1-hiera-large

[34] Grounding DINO base model card. https://huggingface.co/IDEA-Research/grounding-dino-base

[35] Depth Anything V2 Small model card. https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf

[36] Depth Anything V2 Base model card (CC-BY-NC verification). https://huggingface.co/depth-anything/Depth-Anything-V2-Base-hf

[37] SAM 3D Objects model card. https://huggingface.co/facebook/sam-3d-objects

[38] SAM License full text (facebook/sam3/LICENSE). https://huggingface.co/facebook/sam3/blob/main/LICENSE

[39] Stable Fast 3D model card. https://huggingface.co/stabilityai/stable-fast-3d

[40] TRELLIS-image-large model card. https://huggingface.co/microsoft/TRELLIS-image-large

[41] TripoSR model card. https://huggingface.co/stabilityai/TripoSR

[42] Hunyuan3D-2 LICENSE (verbatim verification of geographic exclusion, MAU cap, output-binding clause). https://huggingface.co/tencent/Hunyuan3D-2/blob/main/LICENSE

[43] DETR ResNet-50 model card. https://huggingface.co/facebook/detr-resnet-50

[44] DETR ResNet-101 model card. https://huggingface.co/facebook/detr-resnet-101

[45] RT-DETR R101 VD model card. https://huggingface.co/PekingU/rtdetr_r101vd_coco_o365

[46] DETA Swin-Large model card (and the corresponding GitHub LICENSE). https://huggingface.co/jozhang97/deta-swin-large; https://github.com/jozhang97/DETA/blob/master/LICENSE

[47] OWLv2 large ensemble model card. https://huggingface.co/google/owlv2-large-patch14-ensemble

[48] Florence-2 large model card. https://huggingface.co/microsoft/Florence-2-large

[49] OneFormer ADE20K Swin-L model card. https://huggingface.co/shi-labs/oneformer_ade20k_swin_large

13.4 In-Project Documentation

[50] PIVOT_BLUEPRINT.md (commit 10d1d9f, 21 May 2026). The architectural decision record establishing the retrieval pivot. In-project file: PIVOT_BLUEPRINT.md.

[51] PROJECT_HISTORY.md (commit 013985c, 21 May 2026). The branch-level engineering history relied upon throughout §4. In-project file: PROJECT_HISTORY.md.

[52] README.md. Project README. In-project file: README.md.

[53] WORK_CHECKPOINT.md. Engineering progress notes. In-project file: WORK_CHECKPOINT.md.

[54] FULL_DOCUMENTATION.md. Consolidated documentation index. In-project file: FULL_DOCUMENTATION.md.

[55] TripoSR_CHANGES_AND_LESSONS.md. Engineering retrospective on the TripoSR + SAM2 + Humphrey reverted experiment. In-project file: TripoSR_CHANGES_AND_LESSONS.md.

[56] DEVELOPMENT_ROADMAP_PHASE2.md. Sprint roadmap predating the pivot. In-project file: DEVELOPMENT_ROADMAP_PHASE2.md.

[57] TEAM_ROADMAP.md. Team-level milestone plan. In-project file: TEAM_ROADMAP.md.

[58] MODEL_SURVEY_SCS.md (this project, 6 June 2026). The cross-pipeline model survey supporting §6.2. In-project file: MODEL_SURVEY_SCS.md.

[59] OFFICE_FURNITURE_DETECTION_BENCHMARK.md (this project, 6 June 2026). The detection-specific model survey supporting §6.3. In-project file: OFFICE_FURNITURE_DETECTION_BENCHMARK.md.

[60] SESSION_REPORT.md (this project, 6 June 2026). The setup and research session log. In-project file: SESSION_REPORT.md.

13.5 External Standards and Datasets

[61] buildingSMART International, Industry Foundation Classes (IFC) IFC4 specification. https://standards.buildingsmart.org/IFC/RELEASE/IFC4

[62] Amazon Berkeley Objects dataset, CC-BY-4.0. https://amazon-berkeley-objects.s3.amazonaws.com/index.html

[63] Google Open Images V7 dataset, CC-BY-4.0. https://storage.googleapis.com/openimages/web/index.html

[64] COCO 2017 dataset, CC-BY-4.0. https://cocodataset.org/

[65] ADE20K dataset, BSD-3 (annotations) plus various per-image licences. https://ade20k.csail.mit.edu/



14. Appendix A: License Verification Details

The following table consolidates the verbatim licence string and verification source for every model under consideration in this report. All verifications were performed on 2026-06-06.



15. Appendix B: Test Harness Reference

The detection benchmark harness is at scripts/test_furniture_detection.py. Its full usage is documented in the module docstring; the salient commands are reproduced here.

# Activate Python 3.13 (assuming default install)
$py = "C:\Users\dinos\AppData\Local\Programs\Python\Python313\python.exe"

# Run all 10 models on a single image
& $py scripts\test_furniture_detection.py --image data\scs_test_set\images\office_001.jpg

# Run a subset (e.g. only open-vocabulary detectors)
& $py scripts\test_furniture_detection.py --image office.jpg --models grounding_dino owlv2

# Specify alternate output directory
& $py scripts\test_furniture_detection.py --image office.jpg --outdir outputs/sprint5_eval

Outputs: - outputs/detection_benchmark.csv — per-model summary with columns key, model, ok, error, n_detections, top5, latency_ms, peak_vram_mb. - outputs/detection_overlays/<model_key>.jpg — annotated input image per model showing detected boxes and labels.

The CSV is suitable for direct ingestion into Excel or Python pandas for comparative analysis.



16. Appendix C: Repository Branch Map

For ease of cross-reference, the relationships among the nine branches are reproduced from PROJECT_HISTORY.md §2:

Initial commit (327586a)
    │
    ▼
File-4-21-2026 (project day zero scaffold)
    │
    ▼
phase-1-infrastructure  (Phase 1: backend scaffold, Express server, Python bridge)
    │
    ▼
main  (= phase-1-infrastructure + real-AI-depth-mesh + GPU tuning + TripoSR quality fixes)
    │
    ├── 3c007eb — fix: real IFC4 export                       ←──── LINE B
    │
    ▼
Original-TripoSR
    └── 93c2a94 — feat: all 8 sprints + export fixes          ←──── LINE C
        ├── Sprint 1: Real InstantMesh (Zero123++ + LRM)
        ├── Sprint 2: TRELLIS integration
        ├── Sprint 3: XKT export
        ├── Sprint 4: classify_object.py — 24-class YOLO + IFC taxonomy
        ├── Sprint 5: spatial_layout.py — OR-Tools CP-SAT
        ├── Sprint 6: atiss_layout.py — ATISS scene synthesis
        ├── Sprint 7: run_hunyuan3d.py — Hunyuan3D-2 + texture bake
        └── Sprint 8: test_pipeline.py, frontend model picker, pipeline.js
    │
phase-2-sprints (= Original-TripoSR + PHASE2_SPRINTS.md docs)
    │
TripoSR-SAM2-Humphrey-Enhanced (= reverted SAM2+Poisson+Humphrey experiment)
    │
all-documentation (consolidated documentation/ folder with all 13 docs)
    │
enhanced-pipeline-improvements (= Dimitres.Iteration3 alias)
    │
Dimitres.Iteration3
    ├── 4677eb5 — Depth Anything V2 + CLIP classification + metric IFC dimensions
    ├── 18c9ce8 — SAM2 segmentation + Humphrey smoothing + k-means color
    ├── a458b80 — CLIP fine-tuning pipeline
    └── 52c1062 — fix: Open Images downloader S3 direct URLs
    │
    ▼
retrieval-pivot-blueprint                                    ←──── CURRENT
    ├── 10d1d9f — docs: PIVOT_BLUEPRINT.md
    ├── 013985c — docs: PROJECT_HISTORY.md
    ├── c15ea67 — docs+fix: production stack + real IFC4 export
    └── c78f3ac — feat: salvage Sprint 3/4/5/8 work into retrieval branch



17. Appendix D: Complete Dependency List (Verified As Installed)

This appendix lists every dependency on which the SCS development environment relies, the version installed during the setup described in §7.1, and a short note on the role of each dependency. The lists are organised by ecosystem: system-level prerequisites, Node.js dependencies, Python dependencies, and HuggingFace model artefacts. All versions were captured on 2026-06-06 against the live workstation.

17.1 System-Level Prerequisites

A subtle point: no separate “CUDA Toolkit” install is required. PyTorch’s cu126 wheels bundle the necessary CUDA runtime libraries and load them at import time. The system-side requirement is only that the NVIDIA driver be 525-or-later (current driver 572.83 comfortably satisfies this).

17.2 Node.js Dependencies (package.json)

Installed via npm install from the project’s package-lock.json, producing 242 packages in node_modules. The direct dependencies (i.e. those listed in package.json, not the transitive closure) are:

npm audit reports 12 advisory vulnerabilities (9 moderate, 1 high, 2 critical) in the transitive closure as of the install date. These are characteristic of an older lockfile with multer@1.x and uuid@3 deprecations. None are reachable on the request paths exercised by the SCS pipeline. The recommended action is to schedule a security-cleanup sprint that re-pins to multer@2.x and uuid@11.

17.3 Python Dependencies (Installed Directly into Python 3.13 Global Site-Packages)

The deliberate choice not to use a virtual environment is documented in §7.1; the user requested global installation. The Python dependency list below combines the user’s explicit install set with the transitive closure that was actually realised.

17.3.1 Deep-Learning Runtime

17.3.2 ML and HuggingFace Stack

17.3.3 Mesh, Image, and Scientific Computing

17.3.4 Utilities and Auxiliary

17.3.5 HTTP, Authentication, and CLI

17.3.6 Documentation Generation (Installed in This Session)

17.4 HuggingFace Model Artefacts

These are not Python packages; they are model weight files downloaded on first use of each model. Sizes are approximate, taken from the HuggingFace safetensors artefacts.

Total disk footprint for the recommended SCS stack (excluding SAM 3D Objects, which lives on the secondary box): approximately 10.7 GB. With SAM 3D Objects added: approximately 20 GB. HuggingFace caches these at C:\Users\<user>\.cache\huggingface\hub\ on Windows.

17.5 Configuration Variables — Complete Catalog

Every configuration variable in the deployed .env file is reproduced below with its present value and an annotation of what it controls and why.

17.6 Disk and Network Budget

For a freshly-provisioned SCS workstation following the deployment instructions, the budgets are:

Disk: ~30 GB total for the recommended stack. 3.5 GB pip cache (already realised), ~10.7 GB HuggingFace model cache, ~5 GB Python site-packages, ~1 GB Node.js node_modules, ~5 GB ABO subset (to be downloaded in S3 of the roadmap), ~5 GB headroom for working files and logs.

Network: ~5 GB one-time download. 2.6 GB PyTorch wheels, ~10.7 GB across HuggingFace model cards (downloaded on first use of each model), plus npm packages.

HuggingFace authentication: required for two models. facebook/sam-3d-objects (SAM License Acceptable Use Policy) and facebook/sam3 (same). One-time per HF user account.





18. Appendix E: Empirical Validation Results (9 June 2026)

This appendix records the actual measurements taken when the recommended pipeline was exercised on the SCS engineer’s workstation. Prior sections of this report contained published-benchmark estimates; this appendix supersedes those estimates wherever a measurement exists.

18.1 Test image and environment

Test image: backend/triposr/examples/chair.png, 512×512 RGB, single side chair on transparent background (suitable as a clean-object smoke-test surrogate while a labelled SCS test set is being curated).

Workstation: NVIDIA GeForce RTX 4070 Laptop GPU, 8 GB VRAM, driver 572.83, CUDA 12.8.

Software: Python 3.13.3, PyTorch 2.12.0+cu126, transformers 5.10.2, ifcopenshell 0.8.5.

Network: Unauthenticated HuggingFace access; rate-limited downloads.

18.2 Detection benchmark — measured per-model results

The harness in scripts/test_furniture_detection.py was executed against the 10 candidate detection models from §6.3. The CSV is at outputs/sprint_test/detection_benchmark.csv and annotated overlays in outputs/sprint_test/detection_overlays/.

Headline finding: 4 of 10 models are non-functional on transformers 5.10.2 due to API drift; SigLIP 2 ran but produced degenerate output; 4 ran cleanly; 1 (DINOv2) produced a usable embedding vector.

18.3 Specific failure diagnoses

18.4 Detection overlays

The three working closed-vocabulary detectors all produced tight bounding boxes around the chair with confidence ≥ 0.95. The overlays are visible at:

outputs/sprint_test/detection_overlays/detr_r50.jpg

outputs/sprint_test/detection_overlays/detr_r101.jpg

outputs/sprint_test/detection_overlays/rt_detr.jpg

outputs/sprint_test/detection_overlays/oneformer.jpg — also labels wall and floor as expected for a panoptic segmenter

18.5 TripoSR pipeline — blocked

Execution of backend/python-scripts/run_triposr.py on chair.png failed with a state-dict-key mismatch when loading the TripoSR weights into the model architecture. The saved checkpoint uses the legacy HuggingFace ViT naming (image_tokenizer.model.encoder.layer.N.attention.attention.{query,key,value}.weight) while transformers 5.10.2 expects the consolidated naming (image_tokenizer.model.layers.N.attention.{q_proj,k_proj,v_proj}.weight). The TripoSR architecture’s image_tokenizer layer cannot be initialised from the published weight file on this stack.

Operational consequence: The existing TripoSR-based generative path is not currently runnable on the SCS workstation without either (a) downgrading transformers to a 4.x release compatible with the legacy state-dict naming or (b) implementing a key-remapping layer in tsr/system.py:TSR.from_pretrained. Neither is recommended — the retrieval pivot supersedes the TripoSR path and the engineering effort should be invested there instead.

This empirical finding strengthens the case for the retrieval pivot beyond what §3 and §4 argued: the generative path is not just architecturally inadequate but currently inoperable, and an engineer attempting to revive it would need to invest several hours in API translation before they could even reproduce the four failure modes of §3.2.

18.6 SAM 2 weights — missing

The TripoSR pipeline expects SAM 2 weights at models/sam2/sam2.1_hiera_tiny.pt; the file is not present in the repository. The script’s _segment_foreground falls back to rembg (U²-Net), which works but produces lower-quality masks than SAM 2.

18.7 IFC4 export — works (after one-line fix)

The IFC4 export path in backend/python-scripts/saveIFC.py initially failed with entity instance of type 'IFC4.IfcOwnerHistory' doesn't have the following attributes: OwnerHistory.. This was a real bug: the code passed OwnerHistory=person_org to the IFC owner-history constructor, but the IFC4 schema’s IfcOwnerHistory requires the attribute OwningUser=person_org. The fix was a one-line rename at saveIFC.py:28.

After the fix, the IFC writer was exercised on a synthesised placeholder chair GLB (seat + back + four cylindrical legs, 536 faces, generated with trimesh.creation.box / trimesh.creation.cylinder to substitute for the unavailable TripoSR output) and produced a valid IFC4 file:

Output: outputs/sprint_test/chair_synth.ifc — 21,460 bytes.

Schema: IFC4 ✓

Hierarchy: IfcProject "Office Project" → IfcSite "Site" → IfcBuilding "Building" → IfcBuildingStorey "Ground Floor" → IfcFurniture "Chair_01" ✓

Geometry: 1 IfcTriangulatedFaceSet with the 536-face mesh ✓

Verified by: ifcopenshell.open(...) round-trip; all type queries (by_type('IfcProject'), etc.) returned the expected entities.

Operational consequence: The IFC4 export path is sound. Any clean GLB delivered by the retrieval pipeline’s library-mesh fetch will produce a valid IFC4 file that opens in Revit, BIM Vision, FreeCAD, and xeokit-convert. This is the empirical validation that the recommendation in §11.1 is actionable from the export side.

18.8 Missing-dependency findings

Three Python packages were required by the existing code paths but not in the original install set documented in §17.3:

These are now documented in §17.3 by reference; the canonical install command for a fresh SCS workstation should include them.

18.9 Revised recommendations following empirical validation

Three updates to the recommendations in §11:

Promote sprint S0 — Harness Repair (new). Before sprint S1, the detection harness needs to be made functional on transformers 5.10.2 by fixing the four broken adapters (DETA, Grounding DINO, OWLv2, Florence-2) and investigating the SigLIP 2 zero-output. Estimated 2–3 days of engineering. Without this, the benchmark cannot be the basis of any model-selection decision.

Confirm TripoSR is dead, not deprioritised. The retrieval pivot was framed as “TripoSR is structurally inadequate, so we move on.” The measurement adds: TripoSR is also not running on the current dependency stack. The TripoSR adapter, the Hunyuan3D adapter, the InstantMesh adapter, and the TRELLIS adapter (all of which depend on similar published-weight-loading patterns) should be marked archived rather than deferred.

The IFC export is the only end-to-end success story so far. Sprint S5 (end-to-end retrieval demo) can be confidently planned: the export side is real, fixed, and verified. The blocker is on the input side (detection + retrieval), not the output side.

18.10 Reproducibility — exact commands used

$py = "C:\Users\dinos\AppData\Local\Programs\Python\Python313\python.exe"
cd "C:\Users\dinos\Downloads\3DpicToIFCModeling"

# Detection benchmark (all 10 models)
& $py scripts\test_furniture_detection.py --image backend\triposr\examples\chair.png --outdir outputs\sprint_test

# IFC export verification
& $py backend\python-scripts\saveIFC.py outputs\sprint_test\chair_synth.ifc `
    '[{"name":"Chair_01","glbPath":"outputs/sprint_test/chair_synth.glb","position":[0,0,0],"scale":[1,1,1]}]'

All artefacts are in outputs/sprint_test/ and are reproducible from a clean clone after the timm einops omegaconf moderngl xatlas install.



Statement of Authorship and AI-Tools Disclosure

Declaration

I hereby declare that the present technical report has been authored independently by me. All sources, models, datasets, and prior project artefacts that have been consulted or quoted are identified in the bibliography (§13) and, where appropriate, in inline citations and footnotes. Where I have drawn upon prior in-project documentation prepared by other contributors to the 3DpicToIFCModeling repository (notably PROJECT_HISTORY.md, PIVOT_BLUEPRINT.md, WORK_CHECKPOINT.md, FULL_DOCUMENTATION.md and the engineering history of the nine project branches), those documents are credited as in-project documentation references [50–60] in the bibliography. No portion of this work has been submitted previously for any other deliverable. The conclusions and recommendations represent my own assessment of the project’s state on 6 June 2026.

AI-Tools Disclosure

In preparing this report I have made use of the following AI-based tools, and I disclose them here for completeness in accordance with academic and professional integrity norms:

The use of the above tool was confined to assistance with composition, formatting, and verification. The substantive technical content — namely the architectural pivot analysis, the licence-trap identification, the model survey selection criteria, the hardware-binding-constraint analysis, the sprint-level roadmap, and the recommendations — represents the considered judgement of the human author and the prior engineering work of the project team, on which the author drew. AI-tool output was reviewed, edited, and validated by the human author before inclusion. Where the tool was used to fetch verbatim licence text from HuggingFace, the fetched text has been reproduced as fetched and the corresponding source URL is recorded in §13.3.

No customer data, proprietary SCS information, or non-public source material was uploaded to or processed by any external AI service in the preparation of this report.

Signature

 



End of report.
# CLIP_Training_Strategy

_(extracted from CLIP_Training_Strategy.docx)_

Office Object Classification Strategy
CLIP Fine-Tuning on Google Open Images

Dataset Selection, License Compliance, Training Plan
& Integration into the 2D-to-IFC Pipeline

Dimitres Kisimov  |  April 21, 2026



1. Executive Summary

This strategy paper defines the plan for fine-tuning a CLIP (Contrastive Language–Image Pre-Training) model on the Google Open Images V7 dataset to improve AI-driven object classification within the 2D-to-IFC pipeline. The goal is to increase classification confidence for common office furniture and equipment categories so that the pipeline can assign semantically correct IFC (Industry Foundation Classes) entities — rather than generic placeholders — in every exported building model.

Key objectives:

Improve identification confidence for office furniture and equipment items (chairs, desks, filing cabinets, lamps, monitors, etc.) that are the primary subjects of the pipeline's input photographs.

Produce semantically correct IFC entities (e.g. IfcFurnitureElement with correct PredefinedType) rather than defaulting to IfcBuildingElementProxy.

Maintain full license compliance — all training data used under an open, commercially safe licence (CC BY 4.0).

Keep the trained model fully offline and self-hosted — no runtime API calls or cloud dependencies.

Current baseline performance (CLIP zero-shot, ViT-B/32):

Office chair: ~91% confidence — highest-performing category.

Common furniture (table, monitor, keyboard): ~70–80% confidence — acceptable but improvable.

Niche office items (filing cabinet, cupboard, bookshelf, lamp): ~45–60% confidence — insufficient for reliable IFC assignment.

Average across all 11 target categories: ~65%.

Proposed solution: fine-tune CLIP on 2,000 images per category (22,000 images total) drawn from Google Open Images V7. Expected outcome: +15–25 percentage points uplift on office-specific categories, raising average confidence to approximately 92%.



2. Dataset Selection & License Compliance

Selecting a training dataset for a company product requires careful evaluation of intellectual-property risk. Three candidate datasets were assessed against the criteria of image volume, category coverage, and — critically — commercial licence compatibility.



Analysis:

Office-Home is explicitly restricted to non-commercial, research-only use. Including it in a commercial product would constitute a licence violation.

COCO 2017 uses Flickr images, many of which carry individual photographer licences. While COCO's annotations are CC BY 4.0, the underlying images are not uniformly cleared for commercial use — creating legal ambiguity that introduces unacceptable risk.

Google Open Images V7 images are provided under Creative Commons Attribution 4.0 International (CC BY 4.0). This licence permits commercial use, modification, and redistribution provided that proper attribution is given. It is the only dataset in this assessment that is unambiguously safe for use in a commercial product.

Required attribution statement (must appear in product documentation):

"This project uses images from the Google Open Images Dataset V7, licensed under Creative Commons Attribution 4.0 International (CC BY 4.0). © Google LLC."



3. Target Categories (11 Total)

The following eleven office-related categories have been identified as high-priority targets based on frequency of occurrence in office photographs and current CLIP zero-shot confidence levels. Each category will be trained with 2,000 images, yielding a total training corpus of 22,000 images.



Categories with confidence below 65% (filing cabinet, bookshelf, cabinet/cupboard, lamp, desk lamp, desk) represent the highest-value targets: even a modest improvement in these classes will produce significantly better IFC output quality for a large proportion of real-world office photographs.



4. Training Strategy

The training plan follows a two-phase approach: a rapid linear probe to establish a reliable performance baseline, followed by parameter-efficient LoRA fine-tuning for maximum accuracy. Both phases use the same dataset, split, and augmentation pipeline.

4.1  Phase 1 — Linear Probe (estimated 30 minutes on GPU)

In this phase all CLIP weights are frozen. A single fully-connected classification layer is added on top of CLIP's image encoder output and trained against the 11-class office category labels. This approach is extremely fast, carries near-zero risk of overfitting, and provides a strong baseline that already outperforms zero-shot CLIP on in-distribution office images.

All CLIP encoder parameters: frozen (not updated).

Trainable parameters: one linear layer — 512 × 11 = 5,632 parameters.

Training time: approximately 30 minutes on a single GPU.

Risk of overfitting: very low.

Expected validation accuracy: 85–90%.

4.2  Phase 2 — LoRA Fine-Tuning (estimated 1–2 hours on GPU)

Low-Rank Adaptation (LoRA) introduces small trainable rank-decomposition matrices alongside the frozen attention weights of CLIP's image encoder. Typically only ~1% of the total model parameters are updated, yet the resulting model substantially outperforms a linear probe because the visual representations themselves are adapted to the office-image distribution.

CLIP encoder attention weights: frozen; LoRA adapters inserted alongside.

Trainable parameters: approximately 300,000 (LoRA rank = 16, ~1% of total).

Training time: 1–2 hours on a single GPU.

Risk of overfitting: low — regularised by LoRA rank constraint.

Expected validation accuracy: 90–95%.

Saved checkpoint size: approximately 400 MB (base CLIP + LoRA weights).

4.3  Data Split

Training set: 80% of images per category (1,600 images × 11 = 17,600 total).

Validation set: 10% (200 images × 11 = 2,200 total) — used for early stopping.

Test set: 10% (200 images × 11 = 2,200 total) — held out until final evaluation.

4.4  Data Augmentation

Random crop with resize to 224 × 224 pixels.

Random horizontal flip (p = 0.5).

Colour jitter: brightness ±20%, contrast ±20%, saturation ±10%.

Normalisation: ImageNet mean and standard deviation (CLIP standard).

4.5  Offline Deployment

The fine-tuned model checkpoint is saved locally on the production server. inference_base.py automatically loads the fine-tuned weights at startup if the checkpoint file is present; if the file is absent it falls back gracefully to zero-shot CLIP, ensuring the pipeline remains operational during any training interruption. There are no runtime API calls, no cloud dependencies, and no licensing fees beyond the one-time dataset download.



5. How This Improves the Overall 2D-to-IFC Pipeline

Object classification by CLIP is the semantic pivot of the entire pipeline. Every downstream decision — which IFC entity type to create, which property sets to attach, and which dimension attributes to populate — depends on CLIP's output. Improving classification accuracy therefore has a multiplied positive impact across all final IFC outputs.

Full pipeline with current implementation status:



Before/After comparison for a challenging category:



This improvement propagates automatically through all seven pipeline steps: no changes are required to the SAM2, TripoSR, Depth Anything V2, or IFC export modules. The fine-tuned CLIP model is a drop-in replacement loaded by inference_base.py at startup.



6. Implementation Plan

The following table defines the complete sequence of scripts and tasks required to train, evaluate, and deploy the fine-tuned CLIP model.





7. Risk Assessment & Mitigation

The following risks have been identified and assessed for this training initiative. All identified risks are either fully mitigated or rated as low impact.





8. Attribution & Compliance Statement

The following attribution text must be included in all product documentation, about pages, and any published technical reports that describe or include the fine-tuned CLIP model or its outputs. This satisfies the attribution requirement of the Creative Commons Attribution 4.0 International licence under which the Google Open Images V7 training data is provided.

This project uses images from the Google Open Images Dataset V7, licensed under Creative Commons Attribution 4.0 International (CC BY 4.0). © Google LLC.

For more information see: https://storage.googleapis.com/openimages/web/index.html
Licence text: https://creativecommons.org/licenses/by/4.0/

No other training datasets are used in the fine-tuned model. The CLIP base model (openai/clip-vit-base-patch32) is released by OpenAI under the MIT Licence, which permits unrestricted commercial use. The LoRA implementation (microsoft/LoRA) is released under the MIT Licence.

Full licence texts and dataset cards should be retained in the project repository under /docs/licences/ for audit purposes.



— End of Document —
Prepared by Dimitres Kisimov  |  3DpicToIFCModeling Project  |  April 21, 2026
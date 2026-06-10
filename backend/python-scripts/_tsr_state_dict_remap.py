"""
TripoSR state_dict key remapper.

TripoSR's published weights at stabilityai/TripoSR were saved against the
legacy HuggingFace transformers ViT naming convention (transformers 4.x):
    encoder.layer.N.attention.attention.{query,key,value}.{weight,bias}
    encoder.layer.N.attention.output.dense.{weight,bias}
    encoder.layer.N.intermediate.dense.{weight,bias}
    encoder.layer.N.output.dense.{weight,bias}
    encoder.layer.N.layernorm_{before,after}.{weight,bias}

The transformers 5.x library (which the rest of the SCS pipeline depends on
for DETR / Depth Anything V2 Metric / DINOv2) consolidated this to:
    layers.N.attention.{q_proj,k_proj,v_proj,o_proj}.{weight,bias}
    layers.N.mlp.fc1.{weight,bias}
    layers.N.mlp.fc2.{weight,bias}
    layers.N.layernorm_{before,after}.{weight,bias}

This module provides remap_tsr_state_dict(state_dict) → new_state_dict that
translates the legacy keys to the new naming so TripoSR weights load cleanly
on transformers 5.10.2 without downgrading the rest of the stack.

Verified by inspection of the load error message produced by
backend/triposr/tsr/system.py:TSR.from_pretrained() in the 2026-06-10 session
(see SESSION_2026_06_10_REPORT.md §3 morning entry and TECHNICAL_REPORT_SCS.md
Appendix E §18.5).

Licence: MIT (matches TripoSR).
"""
from __future__ import annotations

import re
from typing import Dict


# ---------------------------------------------------------------------------
# Key rewrite patterns
# ---------------------------------------------------------------------------
# Each pattern is (compiled_regex, replacement_template).
#
# We allow the prefix "image_tokenizer.model." or anywhere ".encoder.layer.N."
# appears, then translate the inside.
#
# CAUTION: layernorm_before and layernorm_after keys retain the same name
# under the new convention — only the path changes from
#     ...encoder.layer.N.layernorm_X     →  ...layers.N.layernorm_X
# so the regex matches the *path-prefix*, not the LN name.
# ---------------------------------------------------------------------------

_PREFIX = r"(?P<prefix>(?:image_tokenizer\.model\.|[^.]+\.)*)encoder\.layer\.(?P<idx>\d+)\."

REMAP_RULES = [
    # query/key/value linear projections inside attention
    (re.compile(_PREFIX + r"attention\.attention\.query\.(?P<kind>weight|bias)$"),
        r"\g<prefix>layers.\g<idx>.attention.q_proj.\g<kind>"),
    (re.compile(_PREFIX + r"attention\.attention\.key\.(?P<kind>weight|bias)$"),
        r"\g<prefix>layers.\g<idx>.attention.k_proj.\g<kind>"),
    (re.compile(_PREFIX + r"attention\.attention\.value\.(?P<kind>weight|bias)$"),
        r"\g<prefix>layers.\g<idx>.attention.v_proj.\g<kind>"),

    # attention output projection
    (re.compile(_PREFIX + r"attention\.output\.dense\.(?P<kind>weight|bias)$"),
        r"\g<prefix>layers.\g<idx>.attention.o_proj.\g<kind>"),

    # MLP (feed-forward) — old: intermediate.dense + output.dense
    #                     new: mlp.fc1 + mlp.fc2
    (re.compile(_PREFIX + r"intermediate\.dense\.(?P<kind>weight|bias)$"),
        r"\g<prefix>layers.\g<idx>.mlp.fc1.\g<kind>"),
    (re.compile(_PREFIX + r"output\.dense\.(?P<kind>weight|bias)$"),
        r"\g<prefix>layers.\g<idx>.mlp.fc2.\g<kind>"),

    # layernorm_before / layernorm_after — name stays the same; only path changes
    (re.compile(_PREFIX + r"layernorm_before\.(?P<kind>weight|bias)$"),
        r"\g<prefix>layers.\g<idx>.layernorm_before.\g<kind>"),
    (re.compile(_PREFIX + r"layernorm_after\.(?P<kind>weight|bias)$"),
        r"\g<prefix>layers.\g<idx>.layernorm_after.\g<kind>"),
]


def remap_tsr_state_dict(state_dict: Dict[str, object]) -> Dict[str, object]:
    """Return a new state_dict with TripoSR's legacy ViT keys renamed to the
    transformers 5.x naming. Keys that don't match any rule are passed through
    untouched. Reports a one-line summary on stdout for traceability."""
    out = {}
    remapped = 0
    passthrough = 0
    for k, v in state_dict.items():
        new_key = k
        for pattern, replacement in REMAP_RULES:
            candidate = pattern.sub(replacement, k)
            if candidate != k:
                new_key = candidate
                break
        if new_key != k:
            remapped += 1
        else:
            passthrough += 1
        out[new_key] = v
    print(
        f"[tsr_remap] state_dict: {remapped} keys remapped, "
        f"{passthrough} passed through",
        flush=True,
    )
    return out


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
def _self_test() -> None:
    """Sanity-check the patterns against a synthetic example."""
    fake = {
        "image_tokenizer.model.encoder.layer.0.attention.attention.query.weight": 1,
        "image_tokenizer.model.encoder.layer.0.attention.attention.key.bias": 2,
        "image_tokenizer.model.encoder.layer.0.attention.attention.value.weight": 3,
        "image_tokenizer.model.encoder.layer.0.attention.output.dense.weight": 4,
        "image_tokenizer.model.encoder.layer.5.intermediate.dense.bias": 5,
        "image_tokenizer.model.encoder.layer.11.output.dense.weight": 6,
        "image_tokenizer.model.encoder.layer.3.layernorm_before.weight": 7,
        "image_tokenizer.model.encoder.layer.3.layernorm_after.bias": 8,
        # Keys that should pass through untouched
        "renderer.something.unrelated": 9,
        "decoder.weight": 10,
    }
    expected_renamed = {
        "image_tokenizer.model.layers.0.attention.q_proj.weight": 1,
        "image_tokenizer.model.layers.0.attention.k_proj.bias": 2,
        "image_tokenizer.model.layers.0.attention.v_proj.weight": 3,
        "image_tokenizer.model.layers.0.attention.o_proj.weight": 4,
        "image_tokenizer.model.layers.5.mlp.fc1.bias": 5,
        "image_tokenizer.model.layers.11.mlp.fc2.weight": 6,
        "image_tokenizer.model.layers.3.layernorm_before.weight": 7,
        "image_tokenizer.model.layers.3.layernorm_after.bias": 8,
        "renderer.something.unrelated": 9,
        "decoder.weight": 10,
    }
    actual = remap_tsr_state_dict(fake)
    for k, v in expected_renamed.items():
        assert k in actual, f"expected key missing: {k}"
        assert actual[k] == v, f"expected key {k} = {v}, got {actual[k]}"
    print("[tsr_remap] self-test OK — 8 keys remapped, 2 pass-through")


if __name__ == "__main__":
    _self_test()

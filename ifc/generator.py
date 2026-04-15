import os
import time

import ifcopenshell
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.api.context
import ifcopenshell.api.project
import ifcopenshell.api.aggregate
import ifcopenshell.api.geometry

import config
from ifc.elements import (
    create_wall,
    create_column,
    create_beam,
    create_slab,
    create_window,
    create_door,
    create_furniture,
)

ELEMENT_BUILDERS = {
    "wall": create_wall,
    "column": create_column,
    "beam": create_beam,
    "slab": create_slab,
    "window": create_window,
    "door": create_door,
    "furniture": create_furniture,
}


def generate_ifc(ai_result: dict, output_name: str | None = None) -> str:
    """Generate an IFC file from the AI analysis result.

    Args:
        ai_result: Dict with ``"elements"`` list from the AI provider.
        output_name: Optional filename (without extension). Defaults to timestamp.

    Returns:
        Absolute path to the written .ifc file.
    """
    elements_data = ai_result.get("elements", [])
    if not elements_data:
        raise ValueError("AI result contains no elements.")

    # --- IFC boilerplate ---
    model = ifcopenshell.api.project.create_file()
    project = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcProject", name="AI Generated Model"
    )
    ifcopenshell.api.unit.assign_unit(model)

    # 3D body context
    ctx_3d = ifcopenshell.api.context.add_context(model, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx_3d,
    )

    # Spatial hierarchy
    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuilding", name="Building"
    )
    storey = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuildingStorey", name="Ground Floor"
    )
    ifcopenshell.api.aggregate.assign_object(
        model, relating_object=project, products=[site]
    )
    ifcopenshell.api.aggregate.assign_object(
        model, relating_object=site, products=[building]
    )
    ifcopenshell.api.aggregate.assign_object(
        model, relating_object=building, products=[storey]
    )

    # --- Create elements ---
    created_walls: list = []
    for elem_data in elements_data:
        elem_type = elem_data.get("type", "").lower()
        builder_fn = ELEMENT_BUILDERS.get(elem_type)
        if builder_fn is None:
            continue

        if elem_type in ("window", "door"):
            entity = builder_fn(model, body, storey, elem_data, created_walls)
        else:
            entity = builder_fn(model, body, storey, elem_data)

        if elem_type == "wall":
            created_walls.append(entity)

    # --- Write file ---
    if output_name is None:
        output_name = f"model_{int(time.time())}"
    output_path = os.path.join(config.OUTPUT_DIR, f"{output_name}.ifc")
    model.write(output_path)
    return output_path

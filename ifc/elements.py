import math

import numpy
import ifcopenshell
import ifcopenshell.api.root
import ifcopenshell.api.geometry
import ifcopenshell.api.spatial
import ifcopenshell.api.feature
import ifcopenshell.util.placement
from ifcopenshell.util.shape_builder import ShapeBuilder, V


def _placement_matrix(x: float, y: float, z: float, angle_deg: float = 0.0):
    """Return a 4x4 placement matrix at (x, y, z) with optional Z-rotation in degrees."""
    mat = numpy.eye(4)
    if angle_deg:
        mat = ifcopenshell.util.placement.rotation(angle_deg, "Z") @ mat
    mat[:, 3][0:3] = (x, y, z)
    return mat


def create_wall(model, body_context, storey, data: dict):
    """Create a wall from start/end points, height, and thickness."""
    wall = ifcopenshell.api.root.create_entity(model, ifc_class="IfcWall")

    sx, sy = data["start"][0], data["start"][1]
    sz = data["start"][2] if len(data["start"]) > 2 else 0.0
    ex, ey = data["end"][0], data["end"][1]
    height = data.get("height", 3.0)
    thickness = data.get("thickness", 0.2)

    representation = ifcopenshell.api.geometry.create_2pt_wall(
        model, element=wall, context=body_context,
        p1=(sx, sy), p2=(ex, ey),
        elevation=sz, height=height, thickness=thickness,
    )

    ifcopenshell.api.spatial.assign_container(
        model, relating_structure=storey, products=[wall]
    )
    return wall


def create_column(model, body_context, storey, data: dict):
    """Create a rectangular column."""
    column = ifcopenshell.api.root.create_entity(model, ifc_class="IfcColumn")

    x, y, z = data["position"][0], data["position"][1], data.get("position", [0, 0, 0])[2] if len(data["position"]) > 2 else 0.0
    w = data.get("width", 0.4)
    d = data.get("depth", 0.4)
    h = data.get("height", 3.0)

    # Place column at position
    matrix = _placement_matrix(x, y, z)
    ifcopenshell.api.geometry.edit_object_placement(model, product=column, matrix=matrix, is_si=True)

    # Rectangular profile (dimensions in project units — meters after assign_unit default)
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileName=f"{w}x{d}",
        ProfileType="AREA",
        XDim=w,
        YDim=d,
    )
    representation = ifcopenshell.api.geometry.add_profile_representation(
        model, context=body_context, profile=profile, depth=h
    )
    ifcopenshell.api.geometry.assign_representation(model, product=column, representation=representation)
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[column])
    return column


def create_beam(model, body_context, storey, data: dict):
    """Create a beam between two 3D points."""
    beam = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBeam")

    sx, sy = data["start"][0], data["start"][1]
    sz = data["start"][2] if len(data["start"]) > 2 else 0.0
    ex, ey = data["end"][0], data["end"][1]
    ez = data["end"][2] if len(data["end"]) > 2 else 0.0

    dx, dy, dz = ex - sx, ey - sy, ez - sz
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-6:
        length = 1.0

    w = data.get("width", 0.3)
    h = data.get("height", 0.5)

    # Angle in XY plane
    angle = math.degrees(math.atan2(dy, dx))

    # Beam extrudes along +Z, so we rotate: first lay it on its side (rotate -90 around Y),
    # then rotate to the correct angle in plan
    mat = numpy.eye(4)
    # Rotate to lay beam along +X (extrusion along +Z → rotate -90 around Y)
    ry = numpy.array([
        [0, 0, -1, 0],
        [0, 1, 0, 0],
        [1, 0, 0, 0],
        [0, 0, 0, 1],
    ], dtype=float)
    mat = ry @ mat
    # Then rotate around Z for plan angle
    if angle:
        mat = ifcopenshell.util.placement.rotation(angle, "Z") @ mat
    mat[:, 3][0:3] = (sx, sy, sz)

    ifcopenshell.api.geometry.edit_object_placement(model, product=beam, matrix=mat, is_si=True)

    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileName=f"{w}x{h}",
        ProfileType="AREA",
        XDim=w,
        YDim=h,
    )
    representation = ifcopenshell.api.geometry.add_profile_representation(
        model, context=body_context, profile=profile, depth=length
    )
    ifcopenshell.api.geometry.assign_representation(model, product=beam, representation=representation)
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[beam])
    return beam


def create_slab(model, body_context, storey, data: dict):
    """Create a slab from a 2D polygon and thickness."""
    slab = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSlab")

    points = data.get("points", [[0, 0], [5, 0], [5, 5], [0, 5]])
    thickness = data.get("thickness", 0.2)
    elevation = data.get("elevation", 0.0)

    matrix = _placement_matrix(0, 0, elevation)
    ifcopenshell.api.geometry.edit_object_placement(model, product=slab, matrix=matrix, is_si=True)

    builder = ShapeBuilder(model)
    pts = [(float(p[0]), float(p[1])) for p in points]
    outer_curve = builder.polyline(pts, closed=True)
    profile = builder.profile(outer_curve)
    slab_solid = builder.extrude(profile, thickness)

    body = body_context
    representation = builder.get_representation(context=body, items=[slab_solid])
    ifcopenshell.api.geometry.assign_representation(model, product=slab, representation=representation)
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[slab])
    return slab


def create_window(model, body_context, storey, data: dict, walls: list):
    """Create a window as a simple box, optionally cutting into a host wall."""
    window = ifcopenshell.api.root.create_entity(model, ifc_class="IfcWindow")

    x, y = data["position"][0], data["position"][1]
    z = data["position"][2] if len(data["position"]) > 2 else 1.0
    w = data.get("width", 1.2)
    h = data.get("height", 1.5)
    depth = 0.2  # window depth (matches typical wall thickness)

    matrix = _placement_matrix(x, y, z)
    ifcopenshell.api.geometry.edit_object_placement(model, product=window, matrix=matrix, is_si=True)

    # Simple box mesh for the window
    vertices = [[(0, 0, 0), (w, 0, 0), (w, depth, 0), (0, depth, 0),
                 (0, 0, h), (w, 0, h), (w, depth, h), (0, depth, h)]]
    faces = [[(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]]
    representation = ifcopenshell.api.geometry.add_mesh_representation(
        model, context=body_context, vertices=vertices, faces=faces
    )
    ifcopenshell.api.geometry.assign_representation(model, product=window, representation=representation)
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[window])
    return window


def create_door(model, body_context, storey, data: dict, walls: list):
    """Create a door as a simple box."""
    door = ifcopenshell.api.root.create_entity(model, ifc_class="IfcDoor")

    x, y = data["position"][0], data["position"][1]
    z = data["position"][2] if len(data["position"]) > 2 else 0.0
    w = data.get("width", 0.9)
    h = data.get("height", 2.1)
    depth = 0.2

    matrix = _placement_matrix(x, y, z)
    ifcopenshell.api.geometry.edit_object_placement(model, product=door, matrix=matrix, is_si=True)

    vertices = [[(0, 0, 0), (w, 0, 0), (w, depth, 0), (0, depth, 0),
                 (0, 0, h), (w, 0, h), (w, depth, h), (0, depth, h)]]
    faces = [[(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]]
    representation = ifcopenshell.api.geometry.add_mesh_representation(
        model, context=body_context, vertices=vertices, faces=faces
    )
    ifcopenshell.api.geometry.assign_representation(model, product=door, representation=representation)
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[door])
    return door


def create_furniture(model, body_context, storey, data: dict):
    """Create furniture/equipment as IfcBuildingElementProxy with box geometry."""
    proxy = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuildingElementProxy",
        name=data.get("label", "Furniture"),
    )

    x, y = data["position"][0], data["position"][1]
    z = data["position"][2] if len(data["position"]) > 2 else 0.0
    w = data.get("width", 1.0)
    d = data.get("depth", 0.6)
    h = data.get("height", 0.75)

    matrix = _placement_matrix(x, y, z)
    ifcopenshell.api.geometry.edit_object_placement(model, product=proxy, matrix=matrix, is_si=True)

    vertices = [[(0, 0, 0), (w, 0, 0), (w, d, 0), (0, d, 0),
                 (0, 0, h), (w, 0, h), (w, d, h), (0, d, h)]]
    faces = [[(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]]
    representation = ifcopenshell.api.geometry.add_mesh_representation(
        model, context=body_context, vertices=vertices, faces=faces
    )
    ifcopenshell.api.geometry.assign_representation(model, product=proxy, representation=representation)
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[proxy])
    return proxy

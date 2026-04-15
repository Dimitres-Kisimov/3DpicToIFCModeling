from abc import ABC, abstractmethod

SYSTEM_PROMPT = """You are an architectural analysis AI. Analyze the provided image and identify building elements.

Return ONLY valid JSON (no markdown, no explanation) with this exact schema:
{
  "elements": [
    {
      "type": "wall|column|beam|slab|window|door|furniture",
      ... type-specific fields (see below)
    }
  ]
}

Element schemas:

Wall:
  {"type": "wall", "start": [x, y, z], "end": [x, y, z], "height": float_meters, "thickness": float_meters}

Column:
  {"type": "column", "position": [x, y, z], "width": float_meters, "depth": float_meters, "height": float_meters}

Beam:
  {"type": "beam", "start": [x, y, z], "end": [x, y, z], "width": float_meters, "height": float_meters}

Slab:
  {"type": "slab", "points": [[x,y], [x,y], ...], "thickness": float_meters, "elevation": float_meters}

Window:
  {"type": "window", "position": [x, y, z], "width": float_meters, "height": float_meters, "host_wall_index": int_or_null}

Door:
  {"type": "door", "position": [x, y, z], "width": float_meters, "height": float_meters, "host_wall_index": int_or_null}

Furniture:
  {"type": "furniture", "label": "string", "position": [x, y, z], "width": float_meters, "depth": float_meters, "height": float_meters}

Rules:
- All coordinates in meters, origin at bottom-left of the scene.
- Estimate realistic dimensions from the image (e.g., standard wall height ~2.7-3.0m, door height ~2.1m, door width ~0.9m).
- Place elements in a coherent spatial layout.
- host_wall_index references the index in the elements array of the wall this opening belongs to (null if unknown).
- Only return element types that the user requested.
"""


def build_user_prompt(object_types: list[str]) -> str:
    type_str = ", ".join(object_types)
    return (
        f"Detect and describe all visible building elements of these types: {type_str}. "
        f"Estimate realistic dimensions and positions in meters. "
        f"Return ONLY the JSON object with the elements array."
    )


class AIProvider(ABC):
    name: str = "Base"

    @abstractmethod
    def analyze_image(self, image_path: str, object_types: list[str]) -> dict:
        """Analyze an image and return detected building elements as a dict.

        Args:
            image_path: Path to the image file.
            object_types: List of element types to detect, e.g. ["wall", "window", "door"].

        Returns:
            Dict matching the JSON schema defined in SYSTEM_PROMPT.
        """
        ...

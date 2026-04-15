import base64
import json
import re

from huggingface_hub import InferenceClient

import config
from ai.base import AIProvider, SYSTEM_PROMPT, build_user_prompt


class HuggingFaceProvider(AIProvider):
    name = "HuggingFace (Free)"

    MODEL_ID = "meta-llama/Llama-3.2-11B-Vision-Instruct"

    def __init__(self):
        token = config.HF_API_TOKEN or None
        self._client = InferenceClient(
            model=self.MODEL_ID,
            token=token,
        )

    def analyze_image(self, image_path: str, object_types: list[str]) -> dict:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        ext = image_path.rsplit(".", 1)[-1].lower()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")

        image_url = f"data:{mime};base64,{image_data}"

        response = self._client.chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_user_prompt(object_types)},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ],
                },
            ],
            max_tokens=4096,
            temperature=0.2,
        )

        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)

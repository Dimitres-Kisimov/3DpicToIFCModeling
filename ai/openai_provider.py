import base64
import json
import re

from openai import OpenAI

import config
from ai.base import AIProvider, SYSTEM_PROMPT, build_user_prompt


class OpenAIProvider(AIProvider):
    name = "OpenAI (GPT-4o)"

    def __init__(self):
        if not config.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY not set. Add it to your .env file."
            )
        self._client = OpenAI(api_key=config.OPENAI_API_KEY)

    def analyze_image(self, image_path: str, object_types: list[str]) -> dict:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        ext = image_path.rsplit(".", 1)[-1].lower()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")

        response = self._client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_user_prompt(object_types)},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{image_data}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=4096,
            temperature=0.2,
        )

        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)

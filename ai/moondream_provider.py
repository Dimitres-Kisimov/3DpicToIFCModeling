import json
import re

from PIL import Image
from transformers import AutoModelForCausalLM, AutoTokenizer

from ai.base import AIProvider, SYSTEM_PROMPT, build_user_prompt


class MoondreamProvider(AIProvider):
    name = "Moondream (Local/Free)"

    MODEL_ID = "vikhyatk/moondream2"

    def __init__(self):
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.MODEL_ID, trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self.MODEL_ID, trust_remote_code=True
        )
        self._model.eval()

    def analyze_image(self, image_path: str, object_types: list[str]) -> dict:
        image = Image.open(image_path).convert("RGB")

        prompt = (
            SYSTEM_PROMPT
            + "\n\n"
            + build_user_prompt(object_types)
        )

        enc_image = self._model.encode_image(image)
        raw = self._model.answer_question(enc_image, prompt, self._tokenizer)

        raw = raw.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Moondream may produce imperfect JSON; try to extract it
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            # Return a minimal valid response as fallback
            return {"elements": []}

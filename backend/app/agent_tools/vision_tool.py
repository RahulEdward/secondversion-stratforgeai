"""Vision tool — analyze images (charts, screenshots, diagrams) using the LLM's vision capability.

Supports: PNG, JPG, JPEG, GIF, WEBP
Works with: Anthropic Claude (vision), OpenAI GPT-4o (vision), Google Gemini (vision)

The tool reads the image file, base64-encodes it, and sends it to the active
LLM provider as a vision message. The LLM describes/analyzes what it sees.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

from app.agents.tools import BaseTool
from app.agent_tools.path_utils import safe_path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB


def _mime_type(ext: str) -> str:
    """Return MIME type for image extension."""
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/png")


def analyze_image(file_path: str, question: str = "") -> str:
    """Analyze an image using the active LLM's vision capability.

    Args:
        file_path: Path to the image file.
        question: Optional question about the image. Default: "Describe and analyze this image in detail."

    Returns:
        JSON with the LLM's analysis.
    """
    try:
        path = safe_path(file_path)
    except ValueError as exc:
        return json.dumps({"status": "error", "error": str(exc)})

    if not path.exists():
        return json.dumps({"status": "error", "error": f"File not found: {file_path}"})

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return json.dumps({
            "status": "error",
            "error": f"Unsupported image format '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        })

    if path.stat().st_size > MAX_IMAGE_SIZE:
        return json.dumps({"status": "error", "error": f"Image too large (max {MAX_IMAGE_SIZE // 1024 // 1024}MB)"})

    # Read and encode
    image_data = path.read_bytes()
    b64 = base64.b64encode(image_data).decode("utf-8")
    mime = _mime_type(ext)

    prompt = question.strip() if question.strip() else (
        "Analyze this image in detail. If it's a chart, describe:\n"
        "- The type of chart (candlestick, line, bar, etc.)\n"
        "- The instrument and timeframe if visible\n"
        "- Key price levels, support/resistance\n"
        "- Any patterns (head-and-shoulders, triangles, channels, etc.)\n"
        "- Indicator readings if visible (RSI, MACD, etc.)\n"
        "- Overall trend direction and strength\n"
        "- Any notable signals or setups\n"
        "If it's not a chart, describe what you see comprehensively."
    )

    # Call the active LLM with vision
    try:
        from app.agent_llm import ChatLLM, get_active

        provider, model = get_active()
        if not provider:
            return json.dumps({"status": "error", "error": "No active LLM provider. Select a model first."})

        llm = ChatLLM()

        # Build vision message in OpenAI format (our ChatLLM adapter handles
        # conversion to Anthropic/Google format internally)
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64}",
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ]

        response = llm.chat(messages, tools=None, timeout=60)
        analysis = response.content or "No analysis generated."

        return json.dumps({
            "status": "ok",
            "file": str(path.name),
            "analysis": analysis,
        }, ensure_ascii=False)

    except Exception as exc:
        logger.exception("Vision analysis failed")
        return json.dumps({"status": "error", "error": f"Vision analysis failed: {exc}"})


class VisionTool(BaseTool):
    """Analyze images (charts, screenshots, diagrams) using LLM vision."""

    name = "analyze_image"
    description = (
        "Analyze an image file using the LLM's vision capability. "
        "Supports PNG, JPG, GIF, WEBP. Great for analyzing trading charts, "
        "candlestick patterns, indicator screenshots, and technical diagrams. "
        "Returns a detailed text description and analysis."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the image file to analyze",
            },
            "question": {
                "type": "string",
                "description": "Optional specific question about the image (default: general analysis)",
            },
        },
        "required": ["file_path"],
    }
    repeatable = True
    is_readonly = True

    @classmethod
    def check_available(cls) -> bool:
        """Vision requires an active LLM that supports images."""
        return True

    def execute(self, **kwargs) -> str:
        return analyze_image(
            file_path=kwargs["file_path"],
            question=kwargs.get("question", ""),
        )

import asyncio
import base64
import logging
import os
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

import litellm
from PIL import Image

from ..core.mode_manager import ModeManager

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM image analysis using LiteLLM"""

    def __init__(self) -> None:
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.mode_manager = ModeManager()

        # Set LiteLLM configuration
        litellm.set_verbose = os.getenv("LLM_VERBOSE", "false").lower() == "true"

        # Configure API keys from environment
        self._setup_api_keys()

    def _setup_api_keys(self) -> None:
        """Setup API keys for various LLM providers"""
        # OpenAI
        if api_key := os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = api_key

        # Add more providers as needed
        # Anthropic
        if api_key := os.getenv("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = api_key

        # Google
        if api_key := os.getenv("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = api_key

    async def analyze_image(
        self,
        image_data: bytes,
        mode: str = "default",
        preset: Optional[str] = None,
        extract_text: bool = True,
    ) -> Dict:
        """Analyze image using LLM vision model"""
        try:
            # Get the appropriate prompt
            prompt = self.mode_manager.get_mode_prompt(mode, preset)
            if not prompt:
                raise ValueError(f"No prompt found for mode: {mode}, preset: {preset}")

            # Prepare image for LLM
            image_b64 = await self._prepare_image(image_data)

            # Create messages for vision model
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ]

            # Call LLM API
            logger.info(f"Calling LLM API with model: {self.model}")
            response = await asyncio.to_thread(
                litellm.completion,
                model=self.model,
                messages=messages,
                max_tokens=500 if mode == "default" else 800,
                temperature=0.3 if mode == "default" else 0.7,
            )

            # Extract response content
            content = response.choices[0].message.content

            # Parse and structure the response
            analysis = self._structure_response(content, mode, preset, response)

            logger.info(f"Image analysis completed for mode: {mode}")
            return analysis

        except Exception as e:
            logger.error(f"Error analyzing image: {e}")
            raise

    async def _prepare_image(self, image_data: bytes) -> str:
        """Prepare image for LLM by resizing and encoding to base64"""
        try:
            # Open image with PIL
            image = Image.open(BytesIO(image_data))

            # Convert to RGB if necessary
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Resize image if too large (max 1024px on longest side)
            max_size = 1024
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"Resized image to {new_size}")

            # Save to bytes
            output = BytesIO()
            image.save(output, format="JPEG", quality=85, optimize=True)
            image_bytes = output.getvalue()

            # Encode to base64
            return base64.b64encode(image_bytes).decode("utf-8")

        except Exception as e:
            logger.error(f"Error preparing image: {e}")
            raise

    def _structure_response(
        self, content: str, mode: str, preset: Optional[str], llm_response
    ) -> Dict:
        """Structure the LLM response into a standardized format"""

        # Get token usage if available
        token_usage = getattr(llm_response, "usage", None)
        tokens_used = token_usage.total_tokens if token_usage else 0

        # Base analysis structure
        analysis = {
            "description": content.strip(),
            "mode": mode,
            "preset": preset,
            "model": self.model,
            "tokens_used": tokens_used,
            "processing_time": None,  # Will be set by caller
        }

        # Add mode-specific fields
        if mode == "default":
            analysis["text_extracted"] = self._extract_text_from_description(content)
        else:  # artistic mode
            analysis["similar_count"] = 0  # Will be updated by similarity search

        return analysis

    def _extract_text_from_description(self, description: str) -> Optional[str]:
        """Extract quoted text from description if present"""
        # Simple heuristic: look for text in quotes
        import re

        # Look for text in various quote patterns
        patterns = [
            r'"([^"]+)"',  # Double quotes
            r"'([^']+)'",  # Single quotes
            r"text.*?[:\-]\s*[\"']([^\"']+)[\"']",  # "text: 'something'"
            r"says?\s*[\"']([^\"']+)[\"']",  # "says 'something'"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            if matches:
                return matches[0]  # Return first match

        return None

    def format_telegram_response(
        self, analysis: Dict, include_keyboard: bool = True
    ) -> Tuple[str, Optional[Any]]:
        """Format analysis for Telegram with HTML formatting"""
        mode = analysis.get("mode", "default")
        preset = analysis.get("preset")
        description = analysis.get("description", "")

        if mode == "default":
            response = "📸 <b>Image Analysis (Default Mode)</b>\n\n"
            response += f"<b>Description:</b> {self._escape_html(description)}\n\n"

            if text := analysis.get("text_extracted"):
                response += f'<b>Text found:</b> "{self._escape_html(text)}"\n\n'

            processing_time = analysis.get("processing_time", 0)
            response += f"⚡ Processed in {processing_time:.1f}s"

        else:  # artistic mode
            response = f"🎨 <b>Image Analysis (Artistic - {preset})</b>\n\n"
            response += f"<b>Analysis:</b> {self._markdown_to_html(description)}\n\n"

            similar_count = analysis.get("similar_count", 0)
            similar_images = analysis.get("similar_images", [])

            if similar_count > 0:
                response += f"🔍 <b>Similar Images:</b> Found {similar_count} similar images in your collection\n"

                # Show top similar images with similarity scores
                for i, similar in enumerate(similar_images[:3], 1):  # Show top 3
                    similarity_score = similar.get("similarity_score", 0) * 100
                    mode_used = similar.get("mode_used", "unknown")
                    preset_used = similar.get("preset_used", "")
                    mode_display = f"{mode_used.title()}" + (
                        f" - {preset_used}" if preset_used else ""
                    )
                    response += f"  {i}. {similarity_score:.0f}% match - {mode_display} analysis\n"

                if similar_count > 3:
                    response += f"  ... and {similar_count - 3} more similar images\n"
                response += "\n"
            else:
                embedding_enabled = analysis.get("embedding_generated", False)
                if embedding_enabled:
                    response += "🔍 <b>Similar Images:</b> No similar images found yet. Keep uploading!\n\n"
                else:
                    response += "🔍 <b>Similar Images:</b> Embedding generation failed - similarity search unavailable\n\n"

            processing_time = analysis.get("processing_time", 0)
            embedding_status = (
                "enabled" if analysis.get("embedding_generated", False) else "failed"
            )
            response += f"⚡ Processed in {processing_time:.1f}s • 🎯 Vector embeddings {embedding_status}"

        # Create keyboard for reanalysis if requested
        keyboard = None
        if include_keyboard:
            file_id = analysis.get("file_id")
            if file_id:
                from ..bot.keyboard_utils import get_keyboard_utils

                keyboard_utils = get_keyboard_utils()
                keyboard = keyboard_utils.create_reanalysis_keyboard(
                    file_id=file_id, current_mode=mode, current_preset=preset
                )

        return response, keyboard

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters for Telegram HTML formatting"""
        # Only need to escape these characters for HTML formatting
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        return text

    def _markdown_to_html(self, text: str) -> str:
        """Convert basic markdown formatting to HTML for Telegram"""
        import re

        # First escape HTML characters
        text = self._escape_html(text)

        # Convert **bold** to <b>bold</b>
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

        # Convert *italic* to <i>italic</i>
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)

        # Convert numbered lists to proper format
        # Pattern: "1. **Title**: Content" -> "1. <b>Title</b>: Content"
        text = re.sub(r"(\d+)\.\s*\*\*(.*?)\*\*:", r"\1. <b>\2</b>:", text)

        return text


# Global service instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get the global LLM service instance"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service

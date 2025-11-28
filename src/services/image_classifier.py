"""
Image classifier service - classifies images for smart routing
Uses Groq Llama 4 Scout (cheapest) with OpenAI GPT-4o-mini fallback
"""

import base64
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Image classification categories and their routing destinations
IMAGE_CATEGORIES = {
    "screenshot": {
        "destination": "inbox",
        "description": "Screenshots of apps, websites, code, error messages, UI elements",
    },
    "receipt": {
        "destination": "expenses",
        "description": "Receipts, invoices, bills, financial documents, price tags",
    },
    "document": {
        "destination": "inbox",
        "description": "Documents, articles, text-heavy images, PDFs, forms",
    },
    "photo": {
        "destination": "media",
        "description": "Personal photos, nature, people, places, art, memes",
    },
    "diagram": {
        "destination": "research",
        "description": "Charts, graphs, diagrams, flowcharts, technical drawings",
    },
    "other": {
        "destination": "inbox",
        "description": "Anything that doesn't fit other categories",
    },
}

CLASSIFICATION_PROMPT = """Classify this image into exactly ONE category. Respond with ONLY the category name, nothing else.

Categories:
- screenshot: Screenshots of apps, websites, code, error messages, UI elements
- receipt: Receipts, invoices, bills, financial documents, price tags
- document: Documents, articles, text-heavy images, PDFs, forms
- photo: Personal photos, nature, people, places, art, memes
- diagram: Charts, graphs, diagrams, flowcharts, technical drawings
- other: Anything that doesn't fit other categories

Respond with just the category name (e.g., "screenshot" or "receipt")."""


class ImageClassifier:
    """Classifies images using vision models for smart routing"""

    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.groq_model = "meta-llama/llama-4-scout-17b-16e-instruct"
        self.openai_model = "gpt-4o-mini"

    def _encode_image(self, image_path: str) -> Tuple[str, str]:
        """Encode image to base64 and detect mime type"""
        path = Path(image_path)
        suffix = path.suffix.lower()

        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(suffix, "image/jpeg")

        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        return image_data, mime_type

    async def _classify_with_groq(self, image_path: str) -> Optional[str]:
        """Classify image using Groq Llama 4 Scout"""
        if not self.groq_api_key:
            logger.warning("GROQ_API_KEY not set, skipping Groq classification")
            return None

        try:
            image_data, mime_type = self._encode_image(image_path)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.groq_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": CLASSIFICATION_PROMPT},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{mime_type};base64,{image_data}"
                                        },
                                    },
                                ],
                            }
                        ],
                        "max_tokens": 20,
                        "temperature": 0,
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    category = (
                        result["choices"][0]["message"]["content"].strip().lower()
                    )
                    logger.info(f"Groq classified image as: {category}")
                    return category
                else:
                    logger.error(
                        f"Groq API error: {response.status_code} - {response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Groq classification failed: {e}")
            return None

    async def _classify_with_openai(self, image_path: str) -> Optional[str]:
        """Classify image using OpenAI GPT-4o-mini (fallback)"""
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not set, skipping OpenAI classification")
            return None

        try:
            image_data, mime_type = self._encode_image(image_path)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.openai_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": CLASSIFICATION_PROMPT},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{mime_type};base64,{image_data}"
                                        },
                                    },
                                ],
                            }
                        ],
                        "max_tokens": 20,
                        "temperature": 0,
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    category = (
                        result["choices"][0]["message"]["content"].strip().lower()
                    )
                    logger.info(f"OpenAI classified image as: {category}")
                    return category
                else:
                    logger.error(
                        f"OpenAI API error: {response.status_code} - {response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"OpenAI classification failed: {e}")
            return None

    async def classify(self, image_path: str) -> Dict:
        """
        Classify an image and return category with routing destination.
        Uses Groq first, falls back to OpenAI if Groq fails.

        Returns:
            Dict with 'category', 'destination', 'provider' keys
        """
        # Try Groq first (cheaper)
        category = await self._classify_with_groq(image_path)
        provider = "groq"

        # Fallback to OpenAI
        if category is None:
            category = await self._classify_with_openai(image_path)
            provider = "openai"

        # Fallback to default if both fail
        if category is None:
            logger.warning("All classification attempts failed, using default")
            category = "other"
            provider = "default"

        # Normalize category
        category = category.strip().lower()
        if category not in IMAGE_CATEGORIES:
            # Try to match partial category names
            for cat_name in IMAGE_CATEGORIES:
                if cat_name in category or category in cat_name:
                    category = cat_name
                    break
            else:
                category = "other"

        destination = IMAGE_CATEGORIES[category]["destination"]

        logger.info(
            f"Image classified: category={category}, destination={destination}, provider={provider}"
        )

        return {
            "category": category,
            "destination": destination,
            "provider": provider,
        }


# Global service instance
_classifier: Optional[ImageClassifier] = None


def get_image_classifier() -> ImageClassifier:
    """Get the global image classifier instance"""
    global _classifier
    if _classifier is None:
        _classifier = ImageClassifier()
    return _classifier

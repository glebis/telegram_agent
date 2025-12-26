#!/usr/bin/env python3
"""
Carousel Generator - Creates 10-slide carousels from any text input.

Uses Agency neobrutalism branding style and optionally incorporates
photos from the iPhone photo index.

Usage:
    python carousel_generator.py --text "Your content here" --platform instagram
    python carousel_generator.py --file article.md --platform linkedin --photos
    python carousel_generator.py --interactive
"""

import argparse
import asyncio
import json
import os
import random
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Agency Brand Colors
COLORS = {
    "primary": "#e85d04",      # Orange
    "secondary": "#ffd60a",    # Yellow
    "accent": "#3a86ff",       # Blue
    "success": "#38b000",      # Green
    "error": "#d62828",        # Red
    "foreground": "#000000",   # Black
    "background": "#ffffff",   # White
    "muted": "#e5e5e5",        # Gray
}

# Slide type color mapping
SLIDE_COLORS = [
    COLORS["primary"],    # 1. Cover - Orange
    COLORS["accent"],     # 2. Hook - Blue
    COLORS["background"], # 3. Point 1 - White
    COLORS["secondary"],  # 4. Point 2 - Yellow
    COLORS["background"], # 5. Point 3 - White
    COLORS["accent"],     # 6. Point 4 - Blue
    COLORS["background"], # 7. Point 5 - White
    COLORS["secondary"],  # 8. Point 6 - Yellow
    COLORS["primary"],    # 9. Summary - Orange
    COLORS["foreground"], # 10. CTA - Black
]

PLATFORM_SIZES = {
    "instagram": (1080, 1350),  # 4:5 ratio
    "linkedin": (1080, 1080),   # 1:1 ratio
    "instagram_story": (1080, 1920),  # 9:16 ratio
}


@dataclass
class CarouselSlide:
    """Single carousel slide."""
    number: int
    slide_type: str  # cover, hook, point, summary, cta
    headline: str
    body: str
    emoji: str
    background_color: str
    photo_path: Optional[str] = None


DISSECT_PROMPT = '''You are a social media content expert. Analyze the following text and create a 10-slide carousel for {platform}.

TEXT TO ANALYZE:
"""
{text}
"""

Create exactly 10 slides following this structure:
1. COVER: Eye-catching title that makes people stop scrolling
2. HOOK: A provocative question or surprising fact
3-8. POINTS: 6 key insights, tips, or takeaways (one per slide)
9. SUMMARY: Wrap-up of the main message
10. CTA: Call to action (follow, save, share, comment)

For each slide provide:
- headline: Short, punchy text (max 8 words)
- body: Supporting text (max 25 words, can be empty for some slides)
- emoji: One relevant emoji
- slide_type: one of [cover, hook, point, summary, cta]

Respond with valid JSON array:
[
  {{"number": 1, "slide_type": "cover", "headline": "...", "body": "...", "emoji": "🚀"}},
  ...
]

Make it engaging, actionable, and shareable. Use simple language.'''


async def dissect_text_with_llm(text: str, platform: str) -> List[dict]:
    """Use LLM to dissect text into 10 carousel slides."""
    import litellm

    prompt = DISSECT_PROMPT.format(text=text, platform=platform)

    response = await litellm.acompletion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content

    # Parse JSON - handle both array and object with slides key
    data = json.loads(content)
    if isinstance(data, dict):
        slides = data.get("slides", data.get("carousel", []))
    else:
        slides = data

    return slides


def get_photos_for_keywords(keywords: List[str], limit: int = 10) -> List[str]:
    """Find photos matching keywords from the photo index."""
    db_path = Path.home() / "ai_projects/photoimport/photoindex.sqlite"
    assets_path = Path.home() / "ai_projects/photoimport/assets"

    if not db_path.exists():
        return []

    photos = []
    conn = sqlite3.connect(db_path)

    for keyword in keywords:
        query = """
            SELECT filename FROM images
            WHERE is_screenshot = 0
            AND (vision_description LIKE ? OR vision_tags LIKE ? OR objects LIKE ?)
            AND vision_done = 1
            ORDER BY RANDOM()
            LIMIT ?
        """
        pattern = f"%{keyword}%"
        cursor = conn.execute(query, (pattern, pattern, pattern, limit))

        for row in cursor:
            photo_path = assets_path / row[0]
            if photo_path.exists():
                photos.append(str(photo_path))

    conn.close()
    return photos[:limit]


def generate_slide_html(slide: CarouselSlide, width: int, height: int) -> str:
    """Generate HTML for a single slide with Agency branding."""

    # Determine text color based on background
    bg = slide.background_color.lower()
    text_color = "#ffffff" if bg in ["#000000", "#e85d04", "#3a86ff"] else "#000000"
    tag_bg = COLORS["primary"] if bg != COLORS["primary"] else COLORS["secondary"]

    # Photo background style
    photo_style = ""
    overlay = ""
    if slide.photo_path:
        photo_style = f'''
            background-image: url('file://{slide.photo_path}');
            background-size: cover;
            background-position: center;
        '''
        overlay = f'''
            <div style="
                position: absolute;
                top: 0; left: 0; right: 0; bottom: 0;
                background: {slide.background_color};
                opacity: 0.85;
            "></div>
        '''

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500;600&family=Geist+Mono:wght@400;500;700&display=swap');

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    width: {width}px;
    height: {height}px;
    background: {slide.background_color};
    font-family: 'Geist Mono', monospace;
    color: {text_color};
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px;
    position: relative;
    {photo_style}
}}

.overlay {{
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    z-index: 1;
}}

.content {{
    position: relative;
    z-index: 2;
    text-align: center;
    max-width: 90%;
}}

.slide-number {{
    position: absolute;
    top: 40px;
    right: 40px;
    font-size: 24px;
    font-weight: 700;
    opacity: 0.5;
    z-index: 2;
}}

.emoji {{
    font-size: 80px;
    margin-bottom: 40px;
    text-shadow: 4px 4px 0 rgba(0,0,0,0.2);
}}

.tag {{
    display: inline-block;
    background: {tag_bg};
    color: #ffffff;
    padding: 12px 24px;
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 40px;
    border: 3px solid #000;
    box-shadow: 4px 4px 0 #000;
}}

.headline {{
    font-size: {72 if len(slide.headline) < 20 else 56}px;
    font-weight: 700;
    line-height: 1.1;
    margin-bottom: 30px;
    text-shadow: 2px 2px 0 rgba(0,0,0,0.1);
}}

.body {{
    font-family: 'EB Garamond', Georgia, serif;
    font-size: 32px;
    line-height: 1.4;
    opacity: 0.9;
    max-width: 800px;
    margin: 0 auto;
}}

.ascii {{
    font-size: 20px;
    opacity: 0.3;
    margin-top: 50px;
    letter-spacing: 0.1em;
}}

.shapes {{
    position: absolute;
    bottom: 60px;
    display: flex;
    gap: 20px;
    font-size: 32px;
    z-index: 2;
}}

.shape {{
    color: {COLORS["secondary"]};
    text-shadow: 2px 2px 0 #000;
}}
</style>
</head>
<body>
{overlay}
<div class="slide-number">{slide.number}/10</div>

<div class="content">
    <div class="emoji">{slide.emoji}</div>

    <div class="tag">{slide.slide_type.upper()}</div>

    <div class="headline">{slide.headline}</div>

    {"<div class='body'>" + slide.body + "</div>" if slide.body else ""}

    <div class="ascii">{"─" * 30}</div>
</div>

<div class="shapes">
    <span class="shape">▲</span>
    <span class="shape">●</span>
    <span class="shape">■</span>
</div>
</body>
</html>'''


async def render_html_to_png(html_content: str, output_path: Path, width: int, height: int):
    """Render HTML to PNG using Playwright."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.set_content(html_content)
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=str(output_path))
        await browser.close()


async def generate_carousel(
    text: str,
    platform: str = "instagram",
    output_dir: Optional[Path] = None,
    use_photos: bool = False,
) -> List[Path]:
    """Generate a 10-slide carousel from input text."""

    width, height = PLATFORM_SIZES.get(platform, PLATFORM_SIZES["instagram"])

    # Create output directory
    if output_dir is None:
        output_dir = Path.cwd() / "carousel_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📝 Analyzing text and creating {platform} carousel...")

    # Dissect text with LLM
    slides_data = await dissect_text_with_llm(text, platform)

    # Optionally find matching photos
    photos = []
    if use_photos:
        keywords = [s.get("headline", "").split()[:2] for s in slides_data]
        flat_keywords = [w for words in keywords for w in words if len(w) > 3]
        photos = get_photos_for_keywords(flat_keywords)
        print(f"📸 Found {len(photos)} matching photos")

    # Create slide objects
    slides = []
    for i, data in enumerate(slides_data[:10]):
        slide = CarouselSlide(
            number=i + 1,
            slide_type=data.get("slide_type", "point"),
            headline=data.get("headline", ""),
            body=data.get("body", ""),
            emoji=data.get("emoji", "✨"),
            background_color=SLIDE_COLORS[i],
            photo_path=photos[i] if i < len(photos) and use_photos else None,
        )
        slides.append(slide)

    # Generate and render slides
    output_paths = []
    for slide in slides:
        print(f"  🎨 Rendering slide {slide.number}/10: {slide.headline[:30]}...")

        html = generate_slide_html(slide, width, height)
        output_path = output_dir / f"slide_{slide.number:02d}.png"

        await render_html_to_png(html, output_path, width, height)
        output_paths.append(output_path)

    print(f"\n✅ Carousel generated: {output_dir}")
    return output_paths


def main():
    parser = argparse.ArgumentParser(description="Generate carousel from text")
    parser.add_argument("--text", "-t", help="Text to convert to carousel")
    parser.add_argument("--file", "-f", help="File containing text")
    parser.add_argument("--platform", "-p", default="instagram",
                       choices=["instagram", "linkedin", "instagram_story"])
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--photos", action="store_true", help="Include matching photos")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    # Get input text
    if args.interactive:
        print("📝 Enter your text (press Ctrl+D when done):")
        text = sys.stdin.read()
    elif args.file:
        text = Path(args.file).read_text()
    elif args.text:
        text = args.text
    else:
        parser.print_help()
        return

    output_dir = Path(args.output) if args.output else None

    asyncio.run(generate_carousel(
        text=text,
        platform=args.platform,
        output_dir=output_dir,
        use_photos=args.photos,
    ))


if __name__ == "__main__":
    main()

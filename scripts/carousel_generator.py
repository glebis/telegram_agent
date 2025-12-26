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

# Slide type color mapping (7 slides - richer content)
SLIDE_COLORS = [
    COLORS["primary"],    # 1. Cover - Orange
    COLORS["foreground"], # 2. Problem - Black
    COLORS["accent"],     # 3. Key Insight - Blue
    COLORS["background"], # 4. Deep Dive 1 - White
    COLORS["secondary"],  # 5. Deep Dive 2 - Yellow
    COLORS["background"], # 6. Deep Dive 3 - White
    COLORS["primary"],    # 7. CTA - Orange
]

PLATFORM_SIZES = {
    "instagram": (1080, 1350),  # 4:5 ratio
    "linkedin": (1080, 1080),   # 1:1 ratio
    "instagram_story": (1080, 1920),  # 9:16 ratio
    "mobile": (1080, 1920),     # 9:16 mobile-optimized for PDF
    "mobile_wide": (1920, 1080),  # 16:9 landscape mobile
}


@dataclass
class CarouselSlide:
    """Single carousel slide."""
    number: int
    slide_type: str  # cover, header_only, text_only, content, cta
    headline: str
    subheadline: str
    body: str
    emoji: str
    background_color: str
    total_slides: int = 7
    layout: str = "full"  # full, header_only, text_only
    photo_path: Optional[str] = None


DISSECT_PROMPT = '''You are creating a MOBILE-OPTIMIZED carousel for easy reading on phones. Extract key insights into exactly 7 slides with VARIED LAYOUTS for visual rhythm.

TEXT TO ANALYZE:
"""
{text}
"""

Create exactly 7 slides using these LAYOUT TYPES:

LAYOUT OPTIONS (use variety for visual interest):
- "header_only": Bold headline + emoji on colored background. NO body text. For impact statements.
- "text_only": Body text only, no headline. For detailed explanations that follow a header_only slide.
- "full": Headline + subheadline + body. For key content slides.

RECOMMENDED STRUCTURE:
1. header_only (COVER): Bold hook with number/stat. Colored background.
2. text_only: Expand on the hook - why this matters.
3. header_only: Key insight statement. Different color.
4. text_only: Details, examples, or steps.
5. full: Main actionable content with specifics.
6. header_only: Memorable takeaway phrase.
7. full (CTA): Clear next step.

FOR EACH SLIDE:
- layout: "header_only" | "text_only" | "full"
- headline: Bold, short (3-6 words for mobile). Empty string for text_only.
- subheadline: Supporting phrase. Empty for header_only/text_only.
- body: For text_only: 30-60 words. For full: 20-40 words. Empty for header_only.
- emoji: One emoji (use for all layouts)
- slide_type: cover, insight, content, takeaway, cta

MOBILE RULES:
- Short headlines (fit on one line on phone)
- Large readable text
- Visual variety (alternate header_only and text_only pairs)
- No code blocks or technical formatting

Respond with valid JSON:
{{"slides": [
  {{"number": 1, "layout": "header_only", "slide_type": "cover", "headline": "...", "subheadline": "", "body": "", "emoji": "🚀"}},
  {{"number": 2, "layout": "text_only", "slide_type": "content", "headline": "", "subheadline": "", "body": "Detailed explanation...", "emoji": "📱"}},
  ...
]}}'''


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


def generate_slide_html(slide: CarouselSlide, width: int, height: int, mobile: bool = False) -> str:
    """Generate HTML for a single slide with Agency branding - supports multiple layouts."""

    # Determine text color based on background
    bg = slide.background_color.lower()
    text_color = "#ffffff" if bg in ["#000000", "#e85d04", "#3a86ff"] else "#000000"
    muted_color = "rgba(255,255,255,0.7)" if bg in ["#000000", "#e85d04", "#3a86ff"] else "rgba(0,0,0,0.6)"
    tag_bg = COLORS["primary"] if bg != COLORS["primary"] else COLORS["secondary"]

    # Mobile: larger base sizes
    size_mult = 1.3 if mobile else 1.0

    # Calculate headline size based on length and layout
    headline_len = len(slide.headline) if slide.headline else 0
    if slide.layout == "header_only":
        # Header-only: extra large centered headline
        if headline_len < 12:
            headline_size = int(120 * size_mult)
        elif headline_len < 20:
            headline_size = int(96 * size_mult)
        else:
            headline_size = int(72 * size_mult)
    else:
        # Normal sizing
        if headline_len < 15:
            headline_size = int(96 * size_mult)
        elif headline_len < 25:
            headline_size = int(80 * size_mult)
        elif headline_len < 35:
            headline_size = int(64 * size_mult)
        else:
            headline_size = int(52 * size_mult)

    # Body text size for mobile
    body_size = int(36 * size_mult) if mobile else 32

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

    # Format body text - convert bullet points to HTML
    body_html = ""
    if slide.body:
        body_text = slide.body
        # Check for bullet points
        if "•" in body_text or "- " in body_text or "\n" in body_text:
            lines = body_text.replace("- ", "• ").split("\n")
            body_html = "<ul class='body-list'>"
            for line in lines:
                line = line.strip()
                if line.startswith("• "):
                    body_html += f"<li>{line[2:]}</li>"
                elif line:
                    body_html += f"<li>{line}</li>"
            body_html += "</ul>"
        else:
            body_html = f"<p class='body-text'>{body_text}</p>"

    # Layout-specific content alignment
    layout = slide.layout
    content_align = "center" if layout == "header_only" else "left"
    justify = "center" if layout == "header_only" else "flex-start"
    emoji_size = int(100 * size_mult) if layout == "header_only" else int(64 * size_mult)

    # Generate layout-specific content
    if layout == "header_only":
        content_html = f'''
    <div class="emoji">{slide.emoji}</div>
    <div class="headline">{slide.headline}</div>
'''
    elif layout == "text_only":
        content_html = f'''
    <div class="emoji" style="font-size: {int(48 * size_mult)}px; margin-bottom: 32px;">{slide.emoji}</div>
    {body_html}
'''
    else:  # full layout
        content_html = f'''
    <div class="emoji">{slide.emoji}</div>
    <div class="headline">{slide.headline}</div>
    {"<div class='subheadline'>" + slide.subheadline + "</div>" if slide.subheadline else ""}
    <div class="divider"></div>
    {body_html}
'''

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Geist+Mono:wght@400;500;700;800&display=swap');

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
    justify-content: {justify};
    padding: {int(80 * size_mult)}px {int(70 * size_mult)}px;
    position: relative;
    {photo_style}
}}

.content {{
    position: relative;
    z-index: 2;
    text-align: {content_align};
    width: 100%;
    {"" if layout == "header_only" else "flex: 1;"}
    display: flex;
    flex-direction: column;
    {"align-items: center; justify-content: center;" if layout == "header_only" else ""}
}}

.slide-number {{
    position: absolute;
    top: {int(40 * size_mult)}px;
    right: {int(40 * size_mult)}px;
    font-size: {int(32 * size_mult)}px;
    font-weight: 700;
    opacity: 0.4;
}}

.emoji {{
    font-size: {emoji_size}px;
    margin-bottom: {int(32 * size_mult)}px;
}}

.headline {{
    font-size: {headline_size}px;
    font-weight: 800;
    line-height: 1.1;
    margin-bottom: {int(24 * size_mult)}px;
    letter-spacing: -0.02em;
    {"max-width: 90%;" if layout == "header_only" else ""}
}}

.subheadline {{
    font-family: 'EB Garamond', Georgia, serif;
    font-size: {int(40 * size_mult)}px;
    font-weight: 500;
    line-height: 1.3;
    margin-bottom: {int(30 * size_mult)}px;
    color: {muted_color};
    font-style: italic;
}}

.body-text {{
    font-family: 'EB Garamond', Georgia, serif;
    font-size: {body_size}px;
    line-height: 1.6;
    max-width: 100%;
}}

.body-list {{
    font-family: 'EB Garamond', Georgia, serif;
    font-size: {body_size}px;
    line-height: 1.6;
    list-style: none;
    padding: 0;
    text-align: left;
}}

.body-list li {{
    position: relative;
    padding-left: {int(44 * size_mult)}px;
    margin-bottom: {int(20 * size_mult)}px;
}}

.body-list li::before {{
    content: "→";
    position: absolute;
    left: 0;
    color: {COLORS["primary"] if bg == COLORS["background"] else COLORS["secondary"]};
    font-weight: 700;
}}

.divider {{
    width: 100%;
    height: 4px;
    background: {text_color};
    opacity: 0.2;
    margin: {int(24 * size_mult)}px 0;
}}

.shapes {{
    position: absolute;
    bottom: {int(40 * size_mult)}px;
    left: {int(70 * size_mult)}px;
    display: flex;
    gap: {int(16 * size_mult)}px;
    font-size: {int(28 * size_mult)}px;
}}

.shape {{
    color: {COLORS["secondary"] if bg != COLORS["secondary"] else COLORS["primary"]};
    text-shadow: 2px 2px 0 #000;
}}
</style>
</head>
<body>
<div class="slide-number">{slide.number}/{slide.total_slides}</div>

<div class="content">
{content_html}
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
    output_pdf: bool = False,
) -> List[Path]:
    """Generate a 7-slide information-rich carousel from input text."""

    width, height = PLATFORM_SIZES.get(platform, PLATFORM_SIZES["instagram"])
    num_slides = 7  # Fewer slides, richer content
    mobile = platform in ["mobile", "mobile_wide"]

    # Create output directory
    if output_dir is None:
        output_dir = Path.cwd() / "carousel_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📝 Analyzing text and creating {platform} carousel (7 rich slides)...")

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
    for i, data in enumerate(slides_data[:num_slides]):
        # Get color, cycling if needed
        color_idx = i % len(SLIDE_COLORS)
        slide = CarouselSlide(
            number=i + 1,
            slide_type=data.get("slide_type", "content"),
            headline=data.get("headline", ""),
            subheadline=data.get("subheadline", ""),
            body=data.get("body", ""),
            emoji=data.get("emoji", "✨"),
            background_color=SLIDE_COLORS[color_idx],
            total_slides=num_slides,
            layout=data.get("layout", "full"),
            photo_path=photos[i] if i < len(photos) and use_photos else None,
        )
        slides.append(slide)

    # Generate and render slides
    output_paths = []
    for slide in slides:
        # Truncate headline for display
        display_headline = slide.headline[:35] if slide.headline else f"[{slide.layout}]"
        print(f"  🎨 Rendering slide {slide.number}/{num_slides}: {display_headline}...")

        html = generate_slide_html(slide, width, height, mobile=mobile)
        output_path = output_dir / f"slide_{slide.number:02d}.png"

        await render_html_to_png(html, output_path, width, height)
        output_paths.append(output_path)

    # Generate PDF if requested
    if output_pdf:
        pdf_path = output_dir / "carousel.pdf"
        print(f"  📄 Generating PDF...")
        await generate_pdf(output_paths, pdf_path)
        print(f"  ✅ PDF saved: {pdf_path}")

    print(f"\n✅ Carousel generated: {output_dir}")
    return output_paths


async def generate_pdf(image_paths: List[Path], output_path: Path):
    """Combine PNGs into a single PDF using img2pdf or PIL."""
    try:
        import img2pdf
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert([str(p) for p in image_paths]))
    except ImportError:
        # Fallback to PIL
        from PIL import Image
        images = [Image.open(p).convert("RGB") for p in image_paths]
        images[0].save(output_path, save_all=True, append_images=images[1:])


def main():
    parser = argparse.ArgumentParser(description="Generate carousel from text")
    parser.add_argument("--text", "-t", help="Text to convert to carousel")
    parser.add_argument("--file", "-f", help="File containing text")
    parser.add_argument("--platform", "-p", default="mobile",
                       choices=["instagram", "linkedin", "instagram_story", "mobile", "mobile_wide"])
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--photos", action="store_true", help="Include matching photos")
    parser.add_argument("--pdf", action="store_true", help="Generate PDF in addition to PNGs")
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
        output_pdf=args.pdf,
    ))


if __name__ == "__main__":
    main()

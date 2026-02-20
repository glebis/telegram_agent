## /save-link - Save URL to Obsidian Vault

Fetch a URL's content and save it as a structured note in the Obsidian vault.

### Usage
- `/save-link <url>` — save to inbox (default)
- `/save-link <url> research` — save to Research/
- `/save-link <url> daily` — save to Daily/

### Steps

1. **Determine content type** from the URL:
   - YouTube video → use `yt-dlp` to get metadata, then transcribe if requested
   - LinkedIn video → use `yt-dlp` (NOT manual scraping)
   - GitHub URL → use `gh` CLI (NOT WebFetch)
   - PDF → download and extract with marker-pdf skill
   - Regular web page → use WebFetch tool

2. **Fetch content**:
   For web pages, use the WebFetch tool to fetch and extract content. If WebFetch fails or returns truncated content, fall back to the Firecrawl skill, then tavily-search as last resort.

3. **Determine destination** (default: `inbox`):
   - `inbox` → `~/Research/vault/inbox/`
   - `research` → `~/Research/vault/Research/`
   - `daily` → `~/Research/vault/Daily/`
   - `media` → `~/Research/vault/media/`

4. **Create the note** with this frontmatter format:
   ```markdown
   ---
   url: "<source_url>"
   title: "<page title>"
   captured: "<ISO timestamp>"
   source: claude
   tags: [capture, <topic_tags>]
   ---

   # <Title>

   <Extracted content as clean markdown>

   ## Key Takeaways
   - <3-5 bullet summary>

   ## Source
   [Original article](<source_url>)
   ```

5. **Cross-link**: Search the vault for related existing notes:
   ```bash
   grep -rl "<key_term>" ~/Research/vault/ --include="*.md" | head -10
   ```
   Add `## Related` section with `[[Note Name]]` wiki-links to relevant notes.

6. **Save the file**:
   Filename format: `<sanitized_title>.md` (replace spaces with hyphens, lowercase, remove special chars).
   Write to the destination directory.

7. **Report**: Show the user the file path and a brief summary.

### Examples

**Save a web article:**
```
/save-link https://example.com/article-about-ai
```
Creates: `~/Research/vault/inbox/article-about-ai.md`

**Save to research folder:**
```
/save-link https://arxiv.org/abs/2401.12345 research
```
Creates: `~/Research/vault/Research/paper-title.md`

### Notes
- For video URLs (YouTube, LinkedIn), always try `yt-dlp` first
- For Telegram videos >20MB, use the Telethon skill (NOT Bot API)
- GitHub URLs: always use `gh` CLI, never WebFetch
- Vault path: `~/Research/vault/`
- If the user shares multiple links, process them in parallel
- Add relevant topic tags based on content (e.g., `ai`, `security`, `python`)

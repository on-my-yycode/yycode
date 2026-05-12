---
name: ppt
description: Use when the user asks to create, edit, outline, review, convert, or extract content from PowerPoint presentations. Prefer editable .pptx output, use optional local tools such as python-pptx, Marp, Pandoc, or LibreOffice when available, and provide graceful fallbacks when they are missing.
license: MIT
compatibility: Skill instructions work without extra software. Creating/editing .pptx requires python-pptx or another local generator; exporting to PDF/images requires LibreOffice, PowerPoint, or Marp/Pandoc depending on workflow.
platforms: [macos, linux, windows]
metadata: {"yoyoagent":{"emoji":"📊","category":"documents","requires_optional_bins":["libreoffice","soffice","marp","pandoc"],"requires_optional_python":["python-pptx"],"outputs":["pptx","pdf","png","markdown"]}}
---

# PowerPoint / Presentation Skill

## Overview

Use this skill for presentation work: planning slide decks, generating editable `.pptx` files, converting Markdown to slides, exporting presentations, reviewing slides, and extracting text from existing deck files.

The skill itself does **not** require local software to be installed. It is an instruction layer. Actual file generation or conversion depends on optional local tools. Always detect what is available first and choose the least surprising workflow.

## When to Use

Use this skill when the user asks for:

- A PowerPoint, PPT, PPTX, keynote-style deck, or slide presentation.
- A presentation outline, speaker notes, or slide-by-slide storyboard.
- Converting Markdown or notes into slides.
- Editing or restructuring an existing `.pptx`.
- Extracting text, agenda, or talking points from an existing presentation.
- Exporting slides to PDF or images.

Do not use this skill when a simple prose answer, table, or diagram is enough.

## Dependency Strategy

Before creating or converting files, check which local capabilities exist. Do not assume they are installed.

### Optional tools

| Capability | Preferred local option | Notes |
|---|---|---|
| Create/edit `.pptx` | Python package `python-pptx` | Best default for editable decks. |
| Markdown to slides | Marp CLI `marp` | Good for fast Markdown-first decks; `.pptx` export may require browser dependencies depending on setup. |
| Markdown/doc conversion | Pandoc `pandoc` | Useful for Markdown/HTML/PDF conversion; PPTX output support depends on installed Pandoc. |
| Export `.pptx` to PDF | LibreOffice `libreoffice` / `soffice` | Good cross-platform CLI fallback, but rendering may differ from PowerPoint. |
| Export via native Office | PowerPoint / Keynote | Usually manual or platform-specific automation; ask before using GUI automation. |

### Suggested detection commands

Use safe read-only checks before relying on a tool:

```bash
python - <<'PY'
try:
    import pptx
    print('python-pptx: available')
except Exception as exc:
    print(f'python-pptx: missing ({exc})')
PY

python -m pip show python-pptx
marp --version
pandoc --version
libreoffice --version
soffice --version
```

If a dependency is missing, do not fail immediately. Offer one of these fallbacks:

1. Produce a slide outline in Markdown.
2. Generate a `.md` Marp-compatible deck if Marp is unavailable but the user can render later.
3. Provide a Python script that can generate `.pptx` once `python-pptx` is installed.
4. Ask permission to install the missing dependency if installation is appropriate in the environment.

## Recommended Workflows

### 1. Presentation planning only

Use this when the user asks for structure, content, or messaging but not a file.

1. Clarify audience, goal, duration, language, tone, and desired number of slides if missing.
2. Produce a slide-by-slide outline:
   - slide title
   - key message
   - bullets
   - visual suggestion
   - speaker notes if useful
3. Keep each slide focused on one idea.
4. Ask whether to turn the outline into a file.

### 2. Create an editable `.pptx`

Prefer this for explicit PowerPoint/PPTX output.

1. Check for `python-pptx`.
2. If available, create a small generation script and run it to write the `.pptx`.
3. Use a clean default theme:
   - 16:9 widescreen
   - title slide
   - section/title-and-content slides
   - readable font sizes
   - consistent accent color
   - speaker notes when requested, if supported by the chosen library/workflow
4. Save generated scripts beside the output only if useful to the user; otherwise keep temporary scripts in a temp path.
5. If `python-pptx` is missing, ask whether to install it or generate Markdown/script fallback.

Minimal Python pattern:

```python
from pptx import Presentation
from pptx.util import Inches, Pt

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

slide = prs.slides.add_slide(prs.slide_layouts[0])
slide.shapes.title.text = "Deck Title"
slide.placeholders[1].text = "Subtitle"

slide = prs.slides.add_slide(prs.slide_layouts[1])
slide.shapes.title.text = "Slide Title"
body = slide.placeholders[1].text_frame
body.text = "Main point"
for bullet in ["Supporting point", "Evidence", "Next step"]:
    p = body.add_paragraph()
    p.text = bullet
    p.level = 1
    p.font.size = Pt(24)

prs.save("output.pptx")
```

### 3. Markdown-first deck

Use this when the user wants fast iteration or version-control-friendly slides.

1. Generate a `slides.md` file using Marp-compatible Markdown.
2. Include frontmatter only if appropriate:

```markdown
---
marp: true
theme: default
paginate: true
---

# Title

Subtitle

---

## Slide Title

- Point A
- Point B
```

3. If `marp` is installed, export with:

```bash
marp slides.md --pptx
marp slides.md --pdf
```

4. If Marp is not installed, leave the Markdown deck and explain how to render it later.

### 4. Convert or export an existing deck

Before converting, preserve the original file.

1. Confirm input path exists and output format.
2. Prefer LibreOffice CLI for `.pptx` to `.pdf` conversion when installed:

```bash
libreoffice --headless --convert-to pdf --outdir ./out input.pptx
# or
soffice --headless --convert-to pdf --outdir ./out input.pptx
```

3. Warn that layout fidelity can vary across renderers.
4. If conversion is critical, recommend manual review in PowerPoint/Keynote/LibreOffice.

### 5. Read or analyze an existing `.pptx`

1. Check whether `python-pptx` is available.
2. Extract slide titles and text.
3. Summarize structure, content gaps, consistency, and improvement suggestions.
4. Do not overwrite the original unless explicitly requested.

Example extraction pattern:

```python
from pptx import Presentation

prs = Presentation("input.pptx")
for index, slide in enumerate(prs.slides, start=1):
    texts = []
    for shape in slide.shapes:
        if hasattr(shape, "text") and shape.text.strip():
            texts.append(shape.text.strip())
    print(f"Slide {index}")
    print("\n".join(texts))
```

## Design Guidelines

- Prefer clear narrative over dense slides.
- Use one main message per slide.
- Keep titles action-oriented when possible.
- Use bullets sparingly; prefer concise phrases.
- Include visual suggestions for data, architecture, timelines, and comparisons.
- For technical decks, include assumptions, constraints, trade-offs, and next steps.
- For business decks, include problem, impact, recommendation, plan, and ask.

## Interaction Guidelines

Ask only the missing questions that materially affect the output:

- Audience and goal.
- Desired slide count or presentation duration.
- Language and tone.
- Output format: outline, Markdown, `.pptx`, PDF, or images.
- Branding/theme requirements.
- Whether local dependency installation is allowed.

If the request is simple, proceed with sensible defaults and state them briefly.

## Safety and File Handling

- Treat presentation generation and conversion as local file operations.
- Do not install packages or run GUI automation without user approval.
- Do not overwrite existing files unless the user explicitly asks.
- Prefer writing new outputs with descriptive names, e.g. `deck-v1.pptx`.
- For conversions, keep the source file unchanged.
- For large or sensitive decks, summarize only the requested content and avoid unnecessary copying.

## Fallback Responses

If no PPT-related tooling is installed, still be useful:

- Provide a polished slide outline.
- Provide Marp-compatible Markdown.
- Provide a ready-to-run Python script for `python-pptx`.
- Explain the exact install command appropriate for the platform only after asking or when the user requests it.

Common install options:

```bash
python -m pip install python-pptx
brew install marp-cli
brew install pandoc
brew install --cask libreoffice
```

Use platform-specific alternatives when not on macOS.

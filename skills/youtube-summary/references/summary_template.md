# Extensive YouTube Summary Guidelines & Template

## Core Principles

1. **Always in English**: Regardless of whether the video is in Dutch, English, German, or any other language, translate and synthesize the entire summary into clear, professional **English**.
2. **Exhaustive Depth Over Brevity**: This is **NOT** a high-level TL;DR. The user relies on this summary in Google Drive and Google NotebookLM as a substitute for re-watching the video.
   - Never compress a 10-minute discussion into a single generic sentence like *"The speaker discusses database performance."*
   - Instead, capture **what** the exact bottleneck was, **why** it occurred, **which** metrics/numbers were cited, and **how** the proposed solution works step-by-step.
3. **Chronological Section Coverage**:
   - Work through every `sections` entry in `yt_data.json` (which maps either to creator-defined YouTube chapters or 10-minute intervals).
   - Every section in the video must have a corresponding `###` subsection in your summary.
4. **Clickable Timestamp Links**:
   - Include clickable timestamp links in the format `[[MM:SS]](https://www.youtube.com/watch?v=<VIDEO_ID>&t=<SECONDS>s)` (or `[HH:MM:SS]`) on every section heading and alongside key claims, demonstrations, or quotes.
5. **Google Docs & NotebookLM Formatting Compatibility**:
   - Use standard Markdown (`#`, `##`, `###`, `**bold**`, `*italic*`, bullet lists, numbered lists, standard Markdown tables, and fenced code blocks).
   - Do **not** use raw HTML tags, Mermaid diagrams, or LaTeX math delimiters (`$...$`), as these do not convert cleanly when imported into Google Docs or synced with NotebookLM. Use clean Unicode symbols (`→`, `×`, `≈`, `≤`, `≥`) instead.

---

## Required Markdown Template

Use the exact structure below when writing `temp_workspace/summary_<video_id>.md`:

```markdown
# <Video Title>

| Metadata | Details |
| :--- | :--- |
| **Channel** | <Channel Name> |
| **Video URL** | [<YouTube URL>](<YouTube URL>) |
| **Published Date** | <YYYY-MM-DD> |
| **Duration** | <HH:MM:SS or MM:SS> |
| **Transcript Source** | <Manual Captions / Auto-Generated / Gemini Audio Fallback> (<Original Language>) |

---

## 1. Executive Synthesis & Core Thesis

Provide a rich 2–3 paragraph synthesis covering:
- **Core Thesis / Objective**: What central problem, question, or topic does this video address, and what is the speaker's primary conclusion?
- **Target Audience & Context**: Why does this matter and what background context frames the discussion?
- **Top 5 High-Impact Takeaways**:
  1. **<Takeaway 1 Title>**: <Detailed 2-sentence explanation with concrete specifics.>
  2. **<Takeaway 2 Title>**: <Detailed 2-sentence explanation with concrete specifics.>
  3. **<Takeaway 3 Title>**: <Detailed 2-sentence explanation with concrete specifics.>
  4. **<Takeaway 4 Title>**: <Detailed 2-sentence explanation with concrete specifics.>
  5. **<Takeaway 5 Title>**: <Detailed 2-sentence explanation with concrete specifics.>

---

## 2. Comprehensive Section-by-Section Breakdown

### 2.1 <Chapter or Section Title> ([[MM:SS]](https://www.youtube.com/watch?v=<VIDEO_ID>&t=<SECONDS>s))
- **Core Argument / Topic**: Detailed explanation of what is presented in this segment.
- **Key Details, Mechanics & Evidence**:
  - Break down every technical point, workflow step, comparison, or story shared.
  - Preserve exact numbers, benchmarks, configuration values, names, and dates mentioned.
  - Include sub-bullets for pros/cons, trade-offs, or step-by-step instructions demonstrated in the video.
- **Notable Quote / Insight**: *"<Translated or verbatim key quote from the speaker>"* ([[MM:SS]](https://www.youtube.com/watch?v=<VIDEO_ID>&t=<SECONDS>s))

### 2.2 <Next Chapter or Section Title> ([[MM:SS]](https://www.youtube.com/watch?v=<VIDEO_ID>&t=<SECONDS>s))
*(Repeat thoroughly for every chapter/section of the video without skipping later sections.)*

---

## 3. Frameworks, Models & Technical Concepts

List and define all mental models, architectures, algorithms, methodologies, or domain concepts explained in the video:
- **<Concept / Framework Name>**: Thorough definition and how the speaker applies it in practice.

---

## 4. Tools, Resources, Books & References Mentioned

| Item / Resource | Category | How It Was Discussed / Recommended Use |
| :--- | :--- | :--- |
| **<Name>** | <Tool / Library / Book / Paper / Person> | <Specific context from the video> |

*(If none were mentioned, write "No specific external tools or books were referenced.")*

---

## 5. Actionable Recommendations & Practical Checklist

Concrete steps, best practices, or pitfalls to avoid based on the video:
1. **<Actionable Step 1>**: How and when to apply it, plus common mistakes to avoid.
2. **<Actionable Step 2>**: How and when to apply it, plus common mistakes to avoid.
```

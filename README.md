# Antigravity Skills Repository

Central Git repository for custom **Google Antigravity (`agy` CLI & IDE)** skills shared across workstation and Raspberry Pi (`teamcola` server).

---

## Repository Folder Structure

All individual skills live inside the [`skills/`](./skills/) directory (one subfolder per skill, following the official Antigravity progressive-disclosure layout):

```text
Skills/
├── README.md                        # Repository overview & setup instructions
├── .gitignore                       # Prevents committing .env, OAuth tokens & temp files
├── skills.json                      # Antigravity skills manifest pointing to ./skills
├── install.sh                       # Symlinks all skills into ~/.gemini/config/skills/
└── skills/                          # Add new skills as subdirectories here
    ├── youtube-summary/             # YouTube Extensive Summarizer -> Drive & NotebookLM
    │   ├── SKILL.md
    │   ├── .env.example
    │   ├── requirements.txt
    │   ├── references/
    │   │   └── summary_template.md
    │   └── scripts/
    │       ├── fetch_youtube.py
    │       ├── publish_summary.py
    │       └── setup_google_auth.py
    └── <future-skill-name>/         # Future skills follow the same structure
        ├── SKILL.md
        ├── references/
        └── scripts/
```

---

## How Antigravity Discovers These Skills

Antigravity does **not** require skills to live inside `~/.gemini/antigravity/scratch/`. Instead, it discovers global skills from **`~/.gemini/config/skills/<skill-name>/SKILL.md`** (or via `~/.gemini/config/skills.json`).

Running `./install.sh` creates symlinks from `~/Skills/skills/<skill-name>` into `~/.gemini/config/skills/<skill-name>`. That means:
1. You edit, commit, and push skills directly inside `~/Skills`.
2. On your Raspberry Pi (or any machine), a simple `git pull && ./install.sh` makes every skill immediately available to `agy`.

---

## Quick Setup (Workstation & Raspberry Pi)

```bash
# 1. Clone the repository (if not already cloned)
git clone git@github.com:wouterlanckman/Skills.git ~/Skills
cd ~/Skills

# 2. Link all skills into ~/.gemini/config/skills/
chmod +x install.sh
./install.sh
```

---

## Adding a New Skill Later

1. Create a new folder under `skills/<new-skill-name>/`:
   ```bash
   mkdir -p ~/Skills/skills/<new-skill-name>/{references,scripts}
   ```
2. Add a `SKILL.md` with YAML frontmatter (`name` and `description`).
3. Run `./install.sh` to symlink the new skill into `~/.gemini/config/skills/`.
4. Commit and push to GitHub:
   ```bash
   git add .
   git commit -m "Add <new-skill-name> skill"
   git push
   ```

---

## Included Skills

### 1. [`youtube-summary`](./skills/youtube-summary/SKILL.md)
* **Input**: Any YouTube video URL.
* **Workflow**:
  1. Extracts metadata, chapters, and captions via `yt-dlp` and `youtube-transcript-api` (with automatic `ffmpeg` + Gemini Audio API transcription fallback if subtitles are disabled).
  2. Generates an **extensive, chronological English summary** following [`summary_template.md`](./skills/youtube-summary/references/summary_template.md).
  3. Uploads a standalone native Google Doc to your configured Google Drive folder (`YOUTUBE_DRIVE_FOLDER_ID`).
  4. Appends the formatted summary to your NotebookLM Master Google Doc (`YOUTUBE_MASTER_DOC_ID`).

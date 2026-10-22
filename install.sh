#!/usr/bin/env bash
# ============================================================================
# Antigravity Skills Installer
# 1. Creates a shared Python virtual environment (.venv) in the Skills repo root
# 2. Installs requirements.txt for every skill in ./skills/*
# 3. Symlinks all skills into ~/.gemini/config/skills/
# ============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC_DIR="${REPO_DIR}/skills"
GLOBAL_SKILLS_DIR="${HOME}/.gemini/config/skills"
VENV_DIR="${REPO_DIR}/.venv"

# 1. Ensure shared .venv exists
if [ ! -x "${VENV_DIR}/bin/pip" ]; then
  echo "🐍 Creating Python virtual environment at ${VENV_DIR} ..."
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/pip" install --upgrade pip
fi

mkdir -p "${GLOBAL_SKILLS_DIR}"

echo "🔗 Linking skills and installing dependencies..."

for skill_path in "${SKILLS_SRC_DIR}"/*/; do
  [ -d "${skill_path}" ] || continue
  skill_name="$(basename "${skill_path}")"
  if [ ! -f "${skill_path}/SKILL.md" ]; then
    echo "   ⚠️  Skipping '${skill_name}' (no SKILL.md found)"
    continue
  fi

  if [ -f "${skill_path}/requirements.txt" ]; then
    echo "   📦 Installing Python dependencies for '${skill_name}'..."
    "${VENV_DIR}/bin/pip" install -r "${skill_path}/requirements.txt"
  fi

  target_link="${GLOBAL_SKILLS_DIR}/${skill_name}"
  ln -sfn "${skill_path%/}" "${target_link}"
  echo "   ✅ Linked skill: ${skill_name} -> ${target_link}"
done

echo "🎉 All skills linked and dependencies installed in ${VENV_DIR}!"

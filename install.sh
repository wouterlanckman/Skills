#!/usr/bin/env bash
# ============================================================================
# Antigravity Skills Installer
# Symlinks all skills in ./skills/* into ~/.gemini/config/skills/ so they are
# automatically discovered by both the Antigravity IDE and the `agy` CLI.
# ============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC_DIR="${REPO_DIR}/skills"
GLOBAL_SKILLS_DIR="${HOME}/.gemini/config/skills"

mkdir -p "${GLOBAL_SKILLS_DIR}"

echo "🔗 Linking skills from ${SKILLS_SRC_DIR} -> ${GLOBAL_SKILLS_DIR} ..."

for skill_path in "${SKILLS_SRC_DIR}"/*/; do
  [ -d "${skill_path}" ] || continue
  skill_name="$(basename "${skill_path}")"
  if [ ! -f "${skill_path}/SKILL.md" ]; then
    echo "   ⚠️  Skipping '${skill_name}' (no SKILL.md found)"
    continue
  fi
  target_link="${GLOBAL_SKILLS_DIR}/${skill_name}"
  ln -sfn "${skill_path%/}" "${target_link}"
  echo "   ✅ Linked skill: ${skill_name} -> ${target_link}"
done

echo "🎉 All skills linked! Antigravity (IDE & agy CLI) will now discover them globally."

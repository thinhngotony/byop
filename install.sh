#!/bin/bash
set -e

# =============================================================================
# byop installer — Bring Your Own Provider
# Wire a custom OpenAI-compatible LLM provider into Zed, py.dev, and more.
# https://github.com/thinhngotony/byop
# =============================================================================

REPO="thinhngotony/byop"
BYOP_REPO_URL="${BYOP_REPO_URL:-https://github.com/${REPO}.git}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

CHECK="${GREEN}✓${NC}"
CROSS="${RED}✗${NC}"
WARN="${YELLOW}!${NC}"

info()  { printf "  %b\n" "$1"; }
die()   { printf "  %b %b\n" "$CROSS" "$1" >&2; exit 1; }

# =============================================================================
# Preconditions
# =============================================================================

OS="$(uname -s)"
if [ "$OS" != "Darwin" ]; then
    printf "%b\n" "${YELLOW}byop currently supports macOS only${NC} (it integrates with the macOS keychain)."
    printf "%b\n" "Detected: ${OS}. Aborting."
    exit 1
fi

# Locate a Python >= 3.11 interpreter.
find_python() {
    for cand in python3.13 python3.12 python3.11 python3; do
        if command -v "$cand" >/dev/null 2>&1; then
            if "$cand" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
                echo "$cand"
                return 0
            fi
        fi
    done
    return 1
}

# Resolve the latest release tag (falls back to the default branch).
latest_tag() {
    curl -sfS "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null \
        | grep '"tag_name"' | head -1 \
        | sed 's/.*"tag_name" *: *"//;s/".*//'
}

# =============================================================================
# Main
# =============================================================================

printf "\n"
printf "%b\n" "${BOLD}byop${NC} ${DIM}— Bring Your Own Provider${NC}"
printf "%b\n" "${DIM}Custom OpenAI-compatible LLM provider setup for your AI coding tools${NC}"
printf "\n"

printf "%b\n" "${DIM}Checking prerequisites${NC}"

# --- Homebrew (used to install python/pipx if missing) ---------------------
HAS_BREW=false
command -v brew >/dev/null 2>&1 && HAS_BREW=true

# --- Python ----------------------------------------------------------------
PY="$(find_python || true)"
if [ -z "$PY" ]; then
    if [ "$HAS_BREW" = true ]; then
        info "${WARN} Python 3.11+ not found; installing via Homebrew..."
        brew install python@3.12 >/dev/null 2>&1 || die "Failed to install Python via Homebrew."
        PY="$(find_python || true)"
    fi
fi
[ -n "$PY" ] || die "Python 3.11+ is required. Install it (e.g. 'brew install python') and re-run."
info "${CHECK} Python: ${BOLD}$("$PY" --version 2>&1)${NC}"

# --- pipx (preferred: isolated install) ------------------------------------
INSTALLER=""
if command -v pipx >/dev/null 2>&1; then
    INSTALLER="pipx"
elif [ "$HAS_BREW" = true ]; then
    info "${WARN} pipx not found; installing via Homebrew..."
    if brew install pipx >/dev/null 2>&1; then
        pipx ensurepath >/dev/null 2>&1 || true
        INSTALLER="pipx"
    fi
fi
if [ -z "$INSTALLER" ]; then
    info "${WARN} pipx unavailable; installing byop into your user site with pip."
    INSTALLER="pip"
fi

# --- Determine version to install ------------------------------------------
TAG="$(latest_tag)"
if [ -n "$TAG" ]; then
    SOURCE="git+${BYOP_REPO_URL}@${TAG}"
    info "${CHECK} Latest release: ${BOLD}${TAG}${NC}"
else
    SOURCE="git+${BYOP_REPO_URL}"
    TAG="(default branch)"
    info "${WARN} Could not detect a release; installing from the default branch."
fi

printf "\n"
printf "%b\n" "${DIM}Installing byop ${TAG}${NC}"

if [ "$INSTALLER" = "pipx" ]; then
    if pipx install --force "$SOURCE" >/dev/null 2>&1; then
        info "${CHECK} Installed with pipx"
    else
        die "pipx install failed. Try: pipx install \"$SOURCE\""
    fi
else
    if "$PY" -m pip install --user --upgrade "$SOURCE" >/dev/null 2>&1; then
        info "${CHECK} Installed with pip (--user)"
    else
        die "pip install failed. Try: $PY -m pip install --user \"$SOURCE\""
    fi
fi

# --- Verify ----------------------------------------------------------------
printf "\n"
if command -v byop >/dev/null 2>&1; then
    printf "%b\n" "${GREEN}${BOLD}Installation complete${NC} ${DIM}($(byop --version 2>/dev/null))${NC}"
    printf "\n"
    printf "%b\n" "${DIM}Get started${NC}"
    printf "  %b\n" "${CYAN}byop${NC}            Run the interactive setup wizard"
    printf "  %b\n" "${CYAN}byop --help${NC}     Show all options"
else
    printf "%b\n" "${GREEN}${BOLD}Installation complete${NC}"
    printf "\n"
    printf "%b\n" "${WARN} The ${BOLD}byop${NC} command isn't on your PATH yet."
    if [ "$INSTALLER" = "pipx" ]; then
        printf "%b\n" "  Run: ${CYAN}pipx ensurepath${NC} then open a new terminal."
    else
        printf "%b\n" "  Add your Python user bin to PATH, e.g.:"
        printf "%b\n" "    ${CYAN}export PATH=\"\$($PY -m site --user-base)/bin:\$PATH\"${NC}"
    fi
fi
printf "\n"
printf "%b\n" "${DIM}Documentation${NC}  https://github.com/${REPO}"
printf "\n"

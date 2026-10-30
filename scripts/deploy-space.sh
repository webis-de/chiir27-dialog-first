#!/usr/bin/env bash
# Deploys the committed state of the prototype as a static Hugging Face Space (the live demo), in which the
# backend runs in the browser with Pyodide (scripts/build-static.py). The Space's README.md carries the
# YAML header that Hugging Face requires (sdk: static); the push replaces the Space's content.
# Git asks for the Hugging Face user name and an access token with write permission as password.
# Usage: scripts/deploy-space.sh <user>/<space>   (e.g. dialog-first/demo)
set -euo pipefail

space="${1:?usage: scripts/deploy-space.sh <user>/<space>}"
root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir "$tmp/src"
git -C "$root" archive HEAD | tar -x -C "$tmp/src"
python3 "$tmp/src/scripts/build-static.py" "$tmp/site" >/dev/null
{
  printf -- '---\ntitle: Dialog-First Product Search\nemoji: 💬\ncolorFrom: gray\ncolorTo: blue\n'
  printf -- 'sdk: static\napp_file: index.html\npinned: false\n---\n\n'
  cat "$tmp/src/README.md"
} > "$tmp/site/README.md"

cd "$tmp/site"
git init -q -b main
git add -A
git -c user.name="Dialog-First" -c user.email="dialog-first@users.noreply.huggingface.co" \
  commit -q -m "Deploy $(git -C "$root" rev-parse --short HEAD)"
git push --force "https://huggingface.co/spaces/$space" main
echo "Deployed to https://huggingface.co/spaces/$space"

#!/usr/bin/env bash
# Deploys the committed state of the prototype to a Hugging Face Docker Space (the live demo).
# The Space needs a README.md with a YAML header (sdk: docker), which this repository's README does not
# carry; the script therefore pushes a copy of HEAD with that header prepended, replacing the Space's content.
# Git asks for the Hugging Face user name and an access token with write permission as password.
# Usage: scripts/deploy-space.sh <user>/<space>   (e.g. dialog-first/demo)
set -euo pipefail

space="${1:?usage: scripts/deploy-space.sh <user>/<space>}"
root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$root" archive HEAD | tar -x -C "$tmp"
{
  printf -- '---\ntitle: Dialog-First Product Search\nemoji: 💬\ncolorFrom: gray\ncolorTo: blue\n'
  printf -- 'sdk: docker\napp_port: 7860\npinned: false\n---\n\n'
  cat "$tmp/README.md"
} > "$tmp/README.space.md"
mv "$tmp/README.space.md" "$tmp/README.md"

cd "$tmp"
git init -q -b main
git add -A
git -c user.name="Dialog-First" -c user.email="dialog-first@users.noreply.huggingface.co" \
  commit -q -m "Deploy $(git -C "$root" rev-parse --short HEAD)"
git push --force "https://huggingface.co/spaces/$space" main
echo "Deployed to https://huggingface.co/spaces/$space"

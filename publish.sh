#!/usr/bin/env bash
# One-shot publish for Grass Check. Run from this folder on a machine where
# `gh auth login` is done as arjunkshah12345-hash.
set -euo pipefail
OWNER=arjunkshah12345-hash
REPO=grasscheck
gh repo create "$OWNER/$REPO" --public --source . --remote origin --push \
  --description "Proof you went outside. An open vision model checks your photo on your phone, offline."
# Turn on Pages with GitHub Actions as the source, then run the deploy.
gh api -X POST "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null || \
  gh api -X PUT "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null
gh workflow run pages.yml --repo "$OWNER/$REPO" --ref main || true
echo "Watch: https://github.com/$OWNER/$REPO/actions"
echo "Live (1 to 3 min): https://$OWNER.github.io/$REPO/"

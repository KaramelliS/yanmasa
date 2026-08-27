#!/bin/sh
# Git kancalarını kurar. .git/hooks klonlanmıyor, bu yüzden elle bir adım.
kok=$(git rev-parse --show-toplevel)
cp "$kok/scripts/pre-commit" "$kok/.git/hooks/pre-commit"
chmod +x "$kok/.git/hooks/pre-commit"
echo "pre-commit kancası kuruldu."
# not

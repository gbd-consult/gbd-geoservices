#!/bin/sh
# Regenerate model/generated/ (categories.yaml, classifier.yaml) from model/categories.yaml,
# model/classifier.yaml, model/parameters.yaml and the cached iD / OpenMapTiles sources
# (tools/.cache; downloaded on first run), and warn where the rules and styles/classes.yaml
# disagree. Host-side, needs python3 + PyYAML.
set -eu
cd "$(dirname "$0")/.."
python3 tools/gen_classifier.py

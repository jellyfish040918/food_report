#!/bin/sh
set -eu

# Fail before listening if a provider mount or environment change hides the model.
# The bundled model is a library model with an explicit version tag.
model="${FLAVO_MODEL:-qwen3.5:9b}"
models="${OLLAMA_MODELS:-/opt/flavo/models}"
export OLLAMA_MODELS="$models"
manifest="$models/manifests/registry.ollama.ai/library/${model%:*}/${model##*:}"
if [ ! -s "$manifest" ] || [ ! -d "$models/blobs" ]; then
    echo "FLAVO model files are missing; rebuild the model image before deployment." >&2
    exit 1
fi
if [ -z "$(find "$models/blobs" -type f -name 'sha256-*' -print -quit)" ]; then
    echo "FLAVO model weights are missing; refusing to start an empty model server." >&2
    exit 1
fi
echo "FLAVO bundled model is present: $model"
exec ollama serve

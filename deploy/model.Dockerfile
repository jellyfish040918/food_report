# Model files are part of the image: the 6.5 GB model exceeds Hobby's 5 GB volume limit.
FROM ollama/ollama:0.40.2
ARG FLAVO_MODEL=qwen3.5:9b
ENV OLLAMA_HOST=[::]:11434 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=0 OLLAMA_CONTEXT_LENGTH=8192
RUN ollama serve > /tmp/model-build.log 2>&1 & pid=$!; \
    trap 'kill "$pid" 2>/dev/null || true' EXIT; \
    n=0; until ollama list >/dev/null 2>&1; do n=$((n+1)); [ "$n" -lt 30 ] || exit 1; sleep 1; done; \
    ollama pull "$FLAVO_MODEL"
EXPOSE 11434

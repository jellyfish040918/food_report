# Model files are part of the image: the 6.5 GB model exceeds Hobby's 5 GB volume limit.
FROM ollama/ollama:0.40.2
ARG FLAVO_MODEL=qwen3.5:9b
ENV FLAVO_MODEL=${FLAVO_MODEL} OLLAMA_MODELS=/opt/flavo/models OLLAMA_NO_CLOUD=1 \
    OLLAMA_HOST=[::]:11434 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=0 OLLAMA_CONTEXT_LENGTH=8192
RUN ollama serve > /tmp/model-build.log 2>&1 & pid=$!; \
    trap 'kill "$pid" 2>/dev/null || true' EXIT; \
    n=0; until ollama list >/dev/null 2>&1; do n=$((n+1)); [ "$n" -lt 30 ] || exit 1; sleep 1; done; \
    ollama pull "$FLAVO_MODEL" && ollama show "$FLAVO_MODEL" >/dev/null
# A separate layer checks that the weights really survived the download layer.
RUN test -s "$OLLAMA_MODELS/manifests/registry.ollama.ai/library/${FLAVO_MODEL%:*}/${FLAVO_MODEL##*:}" \
    && test -n "$(find "$OLLAMA_MODELS/blobs" -type f -name 'sha256-*' -print -quit)"
COPY deploy/start-model.sh /opt/flavo/start-model.sh
EXPOSE 11434
ENTRYPOINT []
CMD ["/bin/sh", "/opt/flavo/start-model.sh"]

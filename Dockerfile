FROM node:22-bookworm-slim AS node
FROM python:3.13-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY scripts ./scripts
COPY src ./src
COPY serve.py server.py qa.py qa_en.py index.html ./
RUN python scripts/build.py && useradd --system --uid 10001 flavo && mkdir -p /app/var && chown flavo /app/var
USER flavo
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 FLAVO_DATABASE=/app/var/flavo.sqlite3
EXPOSE 4175
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import os,urllib.request; from urllib.parse import urlparse; r=urllib.request.Request('http://127.0.0.1:4175/api/health',headers={'Host':urlparse(os.environ['FLAVO_PUBLIC_URL']).netloc}); urllib.request.urlopen(r,timeout=4)"
CMD ["python", "serve.py", "--host", "0.0.0.0", "--port", "4175"]

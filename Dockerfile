FROM --platform=linux/amd64 node:22-bookworm-slim AS frontend
WORKDIR /work/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM --platform=linux/amd64 python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglu1-mesa libxrender1 libxext6 libsm6 procps && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md MANIFEST.in ./
COPY docs/licenses/ docs/licenses/
COPY shapeloop/ shapeloop/
COPY --from=frontend /work/frontend/dist/ shapeloop/static/
COPY docs/licenses/frontend/ shapeloop/static/licenses/
COPY THIRD_PARTY_NOTICES.md shapeloop/static/THIRD_PARTY_NOTICES.md
RUN pip install --no-cache-dir .
ENV SHAPELOOP_DATA_DIR=/data
VOLUME /data
# Publish the port on host loopback, for example -p 127.0.0.1:8765:8765.
# The application rejects non-loopback Host and cross-origin mutation requests.
EXPOSE 8765
CMD ["shapeloop-cad", "serve", "--host", "0.0.0.0"]

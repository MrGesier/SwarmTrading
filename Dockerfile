FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DARWIN_AUTOSTART_SYMBOL=BTCUSDT \
    DARWIN_AUTOSTART_MODE=live \
    DARWIN_MARKET_SOURCE=hyperliquid \
    HYPERLIQUID_DATA_NETWORK=mainnet \
    HYPERLIQUID_ENABLED=false \
    DARWIN_LLM_ENABLED=true \
    DARWIN_DATA_DIR=/data
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/ /app/backend/
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist
RUN mkdir -p /data
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]

FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY package*.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig.json ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY backend ./backend
COPY run.py ./
ENV EDGE_MODEL_CACHE=/opt/edgeatlas-models
RUN python run.py warm-model
COPY --from=frontend /build/dist ./dist
RUN useradd --create-home atlas && mkdir -p /app/data && chown -R atlas:atlas /app /opt/edgeatlas-models
USER atlas
ENV EDGE_HOST=0.0.0.0 HF_HUB_OFFLINE=1
EXPOSE 4100
CMD ["python", "run.py", "edge"]

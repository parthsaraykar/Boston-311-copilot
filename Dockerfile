# One image: builds the React UI, then serves UI + API from FastAPI on :8000.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 TOKENIZERS_PARALLELISM=false
COPY requirements.txt .
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
COPY . .
COPY --from=web /web/dist ./web/dist
# pre-download the embedding model so the container works offline
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('paraphrase-multilingual-MiniLM-L12-v2')"
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

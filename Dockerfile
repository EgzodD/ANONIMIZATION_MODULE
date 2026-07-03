FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=300 --retries=5 -r requirements.txt

# Дообученная модель PERSON (ruBERT) — transformers + CPU-torch.
# Ставим CPU-сборку torch (лёгкая ~190МБ) вместо дефолтной CUDA-сборки (~2ГБ).
RUN pip install --no-cache-dir --timeout=600 --retries=5 \
    "transformers>=4.40" torch \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple

RUN python -m spacy download ru_core_news_lg --timeout=300

RUN python -c "\
from natasha import Segmenter, NewsEmbedding, NewsNERTagger; \
emb = NewsEmbedding(); \
NewsNERTagger(emb); \
print('Natasha model ready')"

COPY . .

EXPOSE 8000

RUN adduser --disabled-password --gecos "" appuser
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

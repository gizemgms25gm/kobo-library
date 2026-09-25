FROM python:3.11-slim

WORKDIR /app

# Gerekli sistem araçlarını yükle (Git ve SQLite desteği)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Bağımlılıkları kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyalarını kopyala
COPY . .

# Klasörlerin varlığını garanti et
RUN mkdir -p books static/covers

EXPOSE 5000

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

CMD ["python", "veri.py"]

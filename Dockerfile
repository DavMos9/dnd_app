FROM python:3.11-slim

# Dipendenze di sistema per Pillow (JPEG/PNG)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir \
        flet==0.85.3 \
        "Pillow>=10.0.0"

# Volume per il DB SQLite — montare dall'host per la persistenza
VOLUME ["/root/.dnd_companion"]

EXPOSE 8000

ENV FLET_WEB=true
ENV FLET_PORT=8000

CMD ["python", "main.py"]

FROM python:3.12-slim

# Tesseract z polskim słownikiem — skany i strony z tekstem tylko w obrazie.
# ripgrep — narzędzie szukaj() agenta grepuje strony książek.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-pol ripgrep \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

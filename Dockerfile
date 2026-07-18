# Backend image: runs the FastAPI pipeline service.
# The Streamlit frontend is hosted separately (e.g. Streamlit Community Cloud)
# and reaches this container over HTTP via BACKEND_URL.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

# Hosts inject the port via $PORT (Render/Railway/Fly). Default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Shell form so $PORT is expanded at runtime.
CMD uvicorn api:app --host 0.0.0.0 --port ${PORT}

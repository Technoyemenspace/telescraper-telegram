# Hugging Face Space (cardless free hosting). The app must listen on port 7860.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py rules.py ./

ENV SESSION_DIR=/tmp/telegram

# No CMD shell variables: HF Spaces requires a fixed port.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]

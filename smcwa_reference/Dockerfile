FROM python:3.10-slim

WORKDIR /app

# Install Node.js 20 and Gemini CLI
# These tools are isolated from your Python environment
RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @google/gemini-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Your Python Setup (Unchanged)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "api.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

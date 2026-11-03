FROM node:20-alpine AS contract-build

WORKDIR /contracts
COPY contracts/package*.json ./
RUN npm ci
COPY contracts ./
RUN npx hardhat compile

FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/api ./
COPY scripts /app/scripts
COPY --from=contract-build /contracts/artifacts /contracts/artifacts

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

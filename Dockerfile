FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline/ pipeline/
COPY models/ models/
COPY checks.yml .
CMD ["python", "-m", "pipeline.run"]

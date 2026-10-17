FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements-services.txt ./
RUN pip install --no-cache-dir -r requirements-services.txt
COPY . .
CMD ["python", "-m", "uvicorn", "services.api:app", "--host", "0.0.0.0", "--port", "8000"]

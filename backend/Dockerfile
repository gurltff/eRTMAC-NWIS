FROM python:3.11-slim
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/backend/
COPY data/ /app/data/
ENV NWIS_DATA_DIR=/app/data DATABASE_URL=sqlite:////app/backend/db/nwis.db
RUN mkdir -p /app/backend/db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY server/requirements.txt /app/server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt && useradd --uid 10001 --create-home assistant
COPY server /app/server
USER assistant
EXPOSE 8000
CMD ["uvicorn", "server.mcp.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

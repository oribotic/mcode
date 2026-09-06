FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
	&& poetry install --no-root --only main,remote --no-interaction --no-ansi

COPY shared shared
COPY remote remote

EXPOSE 8000
CMD ["uvicorn", "remote.app:app", "--host", "0.0.0.0", "--port", "8000"]

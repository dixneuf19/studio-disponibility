FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY ./pyproject.toml ./requirements.lock ./
RUN sed '/-e file:./d' requirements.lock > requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /requirements.txt

COPY ./app /app
COPY ./templates ./templates
COPY ./static ./static

ENTRYPOINT ["uvicorn", "app.main:app" , "--host", "0.0.0.0", "--port", "80"]

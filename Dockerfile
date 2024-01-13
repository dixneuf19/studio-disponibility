# Dockerfile
# Uses multi-stage builds requiring Docker 17.05 or higher
# See https://docs.docker.com/develop/develop-images/multistage-build/

# Creating a python base with shared environment variables
FROM python:3.12.1-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

COPY ./pyproject.toml ./requirements.lock ./
RUN sed '/-e file:./d' requirements.lock > requirements.txt
RUN pip install -r /requirements.txt

COPY ./studio-availability /studio-availability

CMD ["uvicorn", "studio-availability.main:app" , "--host", "0.0.0.0", "--port", "80"]

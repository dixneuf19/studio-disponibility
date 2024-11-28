.PHONY: shell install install-dev dev build run push release release-multi deploy

PACKAGE_NAME=app
DOCKER_REPOSITERY=ghcr.io/dixneuf19
IMAGE_NAME=studio-availability
IMAGE_TAG=$(shell git rev-parse --short HEAD)
DOCKER_IMAGE_PATH=$(DOCKER_REPOSITERY)/$(IMAGE_NAME):$(IMAGE_TAG)
SUPPORTED_PLATFORMS=linux/amd64

# Default target
all: dev

install:
	uv sync --no-dev

install-dev:
	uv sync

install-ci:
	uv sync --no-lock

dev:
	uv run uvicorn ${PACKAGE_NAME}.main:app --reload

format:
	uv run ruff format
	uv run ruff check --fix

check-format:
	uv run ruff format --check
	uv run ruff check
	uv run pyright

# test:
# 	uv run pytest --cov=${PACKAGE_NAME} --cov-report=xml tests

build:
	docker build --platform ${SUPPORTED_PLATFORMS} -t $(DOCKER_IMAGE_PATH) . 

docker-run: build
	docker run -p 8000:80 --env-file=.env $(DOCKER_IMAGE_PATH)

push:
	docker buildx build --platform ${SUPPORTED_PLATFORMS} -t $(DOCKER_IMAGE_PATH) . --push

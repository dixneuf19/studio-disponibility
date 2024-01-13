.PHONY: shell install install-dev dev build run push release release-multi deploy

PACKAGE_NAME=src/studio_availability
DOCKER_REPOSITERY=ghcr.io/dixneuf19
IMAGE_NAME=studio-availability
IMAGE_TAG=$(shell git rev-parse --short HEAD)
DOCKER_IMAGE_PATH=$(DOCKER_REPOSITERY)/$(IMAGE_NAME):$(IMAGE_TAG)
SUPPORTED_PLATFORMS=linux/amd64,linux/arm64

# Default target
all: dev

install:
	rye sync --no-dev

install-dev:
	rye sync

install-ci:
	rye sync --no-lock

dev:
	rye run uvicorn ${PACKAGE_NAME}.main:app --reload

format:
	rye run isort .
	rye run black .

check-format:
	rye run isort --check .
	rye run black --check .
	rye run ruff .
	rye run pyright

test:
	rye run pytest --cov=${PACKAGE_NAME} --cov-report=xml tests

build:
	docker buildx build --platform SUPPORTED_PLATFORMS -t $(DOCKER_IMAGE_PATH) .

docker-run: build
	docker run -p 8000:80 --env-file=.env $(DOCKER_IMAGE_PATH)

push:
	docker buildx build --platform SUPPORTED_PLATFORMS -t $(DOCKER_IMAGE_PATH) . --push

secret:
	kubectl create secret generic studio-availability --from-env-file=.env

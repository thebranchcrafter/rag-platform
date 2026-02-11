.PHONY: help build up down restart logs shell db-shell clean install run test format lint migrate prod-build prod-up

# Default target
help:
	@echo "Available targets:"
	@echo "  make build      - Build Docker images"
	@echo "  make up         - Start all services (development)"
	@echo "  make down       - Stop all services"
	@echo "  make restart    - Restart all services"
	@echo "  make logs       - View logs from all services"
	@echo "  make shell       - Access API container shell"
	@echo "  make db-shell    - Access PostgreSQL shell"
	@echo "  make clean       - Remove containers, volumes, and images"
	@echo "  make install     - Install Python dependencies locally"
	@echo "  make run         - Run API locally (requires local PostgreSQL)"
	@echo "  make test        - Run tests (placeholder)"
	@echo "  make format      - Format code with black (if installed)"
	@echo "  make lint        - Lint code with flake8 (if installed)"
	@echo "  make migrate     - Run database migrations"
	@echo "  make prod-build  - Build production images"
	@echo "  make prod-up     - Start services in production mode"

# Docker commands
build:
	docker-compose build

up:
	docker-compose up -d

up-build:
	docker-compose up --build -d

down:
	docker-compose down

down-volumes:
	docker-compose down -v

restart:
	docker-compose restart

logs:
	docker-compose logs -f

logs-api:
	docker-compose logs -f api

logs-db:
	docker-compose logs -f postgres

shell:
	docker-compose exec api /bin/bash

db-shell:
	docker-compose exec postgres psql -U rag_user -d rag_db

clean:
	docker-compose down -v --rmi all
	docker system prune -f

# Local development
install:
	pip install -r requirements.txt

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Testing (placeholder - add your test framework)
test:
	@echo "Add your test command here"
	# pytest tests/

# Code quality (optional - requires black and flake8)
format:
	@if command -v black > /dev/null; then \
		black app/; \
	else \
		echo "black not installed. Install with: pip install black"; \
	fi

lint:
	@if command -v flake8 > /dev/null; then \
		flake8 app/; \
	else \
		echo "flake8 not installed. Install with: pip install flake8"; \
	fi

# Database migrations
migrate:
	docker-compose exec api python -m alembic upgrade head

# Quick start
start: build up
	@echo "Services started. API available at http://localhost:8765"
	@echo "API docs at http://localhost:8765/docs"

stop: down
	@echo "Services stopped"

# Production commands
prod-build:
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml build

prod-up:
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "Production services started. API available at http://localhost:8765"

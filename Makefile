.PHONY: up down logs ps reset check-env

check-env:
	@test -f .env || (echo "Missing .env: copy .env.example to .env and set passwords" && exit 1)

up: check-env
	docker compose up -d --wait

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=100

# Destroys all local data volumes
reset: check-env
	docker compose down -v
	docker compose up -d --wait

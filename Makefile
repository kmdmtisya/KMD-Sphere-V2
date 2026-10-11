.PHONY: up down logs ps reset check-env worker beat dead-letters

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

# Background jobs (P08-T04). Needs the compose stack. The flags are required with RabbitMQ 4
# (it refuses the transient queues of Celery's mingle and gossip); see docs/design/jobs.md.
worker:
	cd backend && uv run celery -A app.worker.celery_app worker -l INFO -P solo -Q default 		--without-mingle --without-gossip --without-heartbeat

beat:
	cd backend && uv run celery -A app.worker.celery_app beat -l INFO

# Failed jobs that need attention (see also the `dead_letter` queue in the RabbitMQ UI)
dead-letters:
	cd backend && uv run python -m app.worker.cli failures

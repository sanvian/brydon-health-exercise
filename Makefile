.PHONY: up down seed logs demo verify remind

seed:
	python3 seeds/generate.py

up:
	docker compose up --build -d
	@echo ""
	@echo "Marketing:  http://www.brydon.localhost:8080"
	@echo "Portal:     http://portal.brydon.localhost:8080"
	@echo "Mail (magic links land here): http://localhost:8025"
	@echo "Tenants:    http://riverside.brydon.localhost:8080  (also: lakeside, maple, harborview, sunrise)"

down:
	docker compose down -v

logs:
	docker compose logs -f directory

# Full isolation proof: distinct data, unroutable cross-tenant DBs,
# per-tenant credentials. See scripts/verify_isolation.sh.
verify:
	@bash scripts/verify_isolation.sh

# Quick isolation proof: same route, different subdomain, different data.
demo:
	@curl -s http://riverside.brydon.localhost:8080/healthz
	@echo ""
	@curl -s http://lakeside.brydon.localhost:8080/healthz
	@echo ""

# Simulate Riverside's reminder job: pre-signed deep link, no discovery
# round-trip. The email lands in Mailpit (http://localhost:8025).
remind:
	@curl -s "http://riverside.brydon.localhost:8080/demo/remind?email=ava.parent@example.com"
	@echo ""

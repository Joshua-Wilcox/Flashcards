.PHONY: dev build run clean install-deps

# Development
dev:
	@echo "Starting development servers..."
	@make -j2 dev-go dev-web

dev-go:
	cd cmd/server && go run .

dev-web:
	cd web && npm run dev

# Build
build: build-web build-go

build-go:
	go build -o bin/server ./cmd/server

build-web:
	cd web && npm run build

# Install dependencies
install-deps:
	go mod download
	cd web && npm install

# Run production build
run: build
	./bin/server

# Clean
clean:
	rm -rf bin/
	rm -rf web/dist/
	rm -rf web/node_modules/

# Database
db-migrate:
	npx supabase db push

# Test
test:
	go test ./...

# Format
fmt:
	go fmt ./...
	cd web && npm run format 2>/dev/null || true

# Lint
lint:
	go vet ./...
	cd web && npm run lint 2>/dev/null || true

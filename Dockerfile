# Stage 1: Build the frontend
FROM node:20-alpine AS frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Build the Go binary
FROM golang:1.22-alpine AS backend
RUN apk add --no-cache git
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
COPY --from=frontend /app/web/dist ./web/dist
RUN CGO_ENABLED=0 GOOS=linux go build -o /server ./cmd/server

# Stage 3: Final minimal image
FROM alpine:3.19
RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=backend /server ./server
COPY --from=frontend /app/web/dist ./web/dist
COPY whitelist.json ./whitelist.json

EXPOSE 2456
ENV PORT=2456
CMD ["./server"]

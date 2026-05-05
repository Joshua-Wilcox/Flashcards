# Flashcards Go + React

A high-performance flashcard application rewritten in Go with a React frontend.

## Architecture

- **Backend**: Go with Chi router, pgxpool for direct PostgreSQL connections
- **Frontend**: React + TypeScript + Vite + TailwindCSS
- **Real-time**: Native Go WebSocket server
- **Database**: PostgreSQL (Supabase-hosted, same schema as original)

## Why This Is Faster

The original Flask app made every database call through the Supabase REST API, adding ~50-150ms of HTTP overhead per call. This Go rewrite connects directly to PostgreSQL via `DATABASE_URL`, executing queries in ~1-5ms.

## Quick Start

### Prerequisites

- Go 1.22+
- Node.js 18+
- PostgreSQL database (Supabase)

### Setup

1. Copy environment variables:
```bash
cp ../.env .env
```

2. Install dependencies:
```bash
make install-deps
```

3. Run development servers:
```bash
make dev
```

This starts:
- Go server on http://localhost:2456
- Vite dev server on http://localhost:3000 (proxies API to Go)

### Production Build

```bash
make build
./bin/server
```

## Project Structure

```
flashcards-go/
├── cmd/server/          # Application entry point
├── internal/
│   ├── auth/            # Discord OAuth, sessions, middleware
│   ├── config/          # Environment configuration
│   ├── db/              # Database pool and queries
│   ├── duplicate/       # TF-IDF semantic duplicate detection
│   ├── handler/         # HTTP handlers
│   ├── realtime/        # WebSocket hub
│   └── security/        # Token generation/verification
├── web/                 # React SPA
│   ├── src/
│   │   ├── api/         # API client and WebSocket
│   │   ├── components/  # React components
│   │   ├── hooks/       # Custom hooks
│   │   ├── pages/       # Page components
│   │   └── types/       # TypeScript types
│   └── ...
├── Makefile
└── go.mod
```

## API Endpoints

### Public
- `GET /api/modules` - List all modules
- `GET /api/leaderboard` - Global leaderboard

### Authenticated
- `POST /api/question` - Get random question
- `POST /api/check-answer` - Submit answer
- `POST /api/filters` - Get filter options
- `GET /api/stats` - User statistics
- `POST /api/submit-flashcard` - Submit new flashcard
- `POST /api/submit-distractor` - Submit distractor
- `POST /api/report-question` - Report issue

### Admin
- `GET /api/admin/submissions` - Pending submissions
- `POST /api/admin/approve-flashcard` - Approve flashcard
- `POST /api/admin/reject-flashcard` - Reject flashcard
- etc.

### External API (n8n compatible)
- `POST /api/ingest_flashcards` - Bulk flashcard ingestion
- `POST /api/submit_distractors` - Bulk distractor submission
- `POST /api/check_duplicates` - Semantic duplicate check
- `POST /api/approve_flashcard` - Approve via API
- `POST /api/reject_flashcard` - Reject via API

## WebSocket

Connect to `/ws` for real-time updates:

```typescript
const ws = new WebSocket('ws://localhost:2456/ws');
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  // message.type: 'activity' | 'leaderboard_update'
  // message.data: ActivityEvent | LeaderboardUpdate
};
```

## Environment Variables

Same as the original Flask app - see `../.env` or `../CLAUDE.md` for details.

Key variables:
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - Session encryption key
- `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` - OAuth credentials
- `N8N_INGEST_TOKEN` - API authentication token

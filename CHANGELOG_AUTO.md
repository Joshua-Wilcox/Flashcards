# Auto-Pilot Changelog

| Date | Change |
|------|--------|
| 2026-05-15 | Migrated admin/PDF access from whitelist.json to `is_admin`/`has_pdf_access` columns on `user_stats` table |
| 2026-05-15 | Display max_streak as subtext ("Best: X") on the Current Streak card in Stats page |
| 2026-05-15 | Add keyboard shortcuts (1-4 keys) to select quiz answers + Enter/Space to advance; visual number badges on desktop |
| 2026-05-15 | Remove broken "Showing X questions" filter count indicator (always showed 1) — cleaned up backend response fields and frontend types |
| 2026-05-15 | Add GET /api/health endpoint returning 200 + DB ping status JSON (useful for monitoring/load balancers) |
| 2026-05-15 | Add POST /api/admin/revoke-pdf-access and POST /api/admin/toggle-admin endpoints with self-toggle guard |
| 2026-05-15 | Add live totals summary bar (total answered, total correct, accuracy %) above leaderboard table with optimistic WebSocket updates |

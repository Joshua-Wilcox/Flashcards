# Auto-Pilot Changelog

| Date | Change |
|------|--------|
| 2026-05-15 | Add personal rank display (#X out of Y players) on Stats page with backend RANK() window function query |
| 2026-05-15 | Migrated admin/PDF access from whitelist.json to `is_admin`/`has_pdf_access` columns on `user_stats` table |
| 2026-05-15 | Display max_streak as subtext ("Best: X") on the Current Streak card in Stats page |
| 2026-05-15 | Add keyboard shortcuts (1-4 keys) to select quiz answers + Enter/Space to advance; visual number badges on desktop |
| 2026-05-15 | Remove broken "Showing X questions" filter count indicator (always showed 1) — cleaned up backend response fields and frontend types |
| 2026-05-15 | Add GET /api/health endpoint returning 200 + DB ping status JSON (useful for monitoring/load balancers) |
| 2026-05-15 | Add POST /api/admin/revoke-pdf-access and POST /api/admin/toggle-admin endpoints with self-toggle guard |
| 2026-05-15 | Add live totals summary bar (total answered, total correct, accuracy %) above leaderboard table with optimistic WebSocket updates |
| 2026-05-15 | Add minimum length validation (10 chars) to report message textarea with inline error and red border on blur/submit |
| 2026-05-15 | Trim form inputs at submission in SubmitFlashcard (question, answer, topic, subtopic, distractors) and ReportForm (message) |
| 2026-05-16 | Add time-since-last-answer badge to Stats page header with gradient styling and formatRelativeTime utility extracted to utils/time.ts |
| 2026-05-16 | Convert live_activity_logs to activity_log (append-only) by removing unique constraint, fixing Recent Activity to always show full entries |
| 2026-05-16 | Add dedicated "Best Streak" card with Crown icon on Stats page, promoting max_streak from subtext to standalone purple card |
| 2026-05-16 | Add server-side request logging middleware (method, path, status, duration, request_id) using zerolog for structured HTTP logging |

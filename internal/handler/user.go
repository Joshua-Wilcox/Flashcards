package handler

import (
	"net/http"

	"flashcards-go/internal/auth"
	"flashcards-go/internal/db/queries"

	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog/log"
)

type UserHandler struct{}

func NewUserHandler() *UserHandler {
	return &UserHandler{}
}

func (h *UserHandler) GetStats(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)

	stats, err := queries.GetUserStats(ctx, userID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get user stats")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal error"})
		return
	}

	if stats == nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "User not found"})
		return
	}

	moduleStats, err := queries.GetUserModuleStats(ctx, userID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get module stats")
		moduleStats = nil
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"user_stats":   stats,
		"module_stats": moduleStats,
	})
}

func (h *UserHandler) GetUserStats(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := chi.URLParam(r, "userID")

	stats, err := queries.GetUserStats(ctx, userID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get user stats")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal error"})
		return
	}

	if stats == nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "User not found"})
		return
	}

	moduleStats, err := queries.GetUserModuleStats(ctx, userID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get module stats")
		moduleStats = nil
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"user_stats":   stats,
		"module_stats": moduleStats,
	})
}

type LeaderboardRequest struct {
	Sort   string `json:"sort"`
	Order  string `json:"order"`
	Module string `json:"module"`
}

func (h *UserHandler) GetLeaderboard(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	sort := r.URL.Query().Get("sort")
	if sort == "" {
		sort = "correct_answers"
	}

	order := r.URL.Query().Get("order")
	if order == "" {
		order = "desc"
	}

	moduleName := r.URL.Query().Get("module")
	var moduleID *int

	if moduleName != "" {
		id, err := queries.GetModuleIDByName(ctx, moduleName)
		if err != nil {
			log.Error().Err(err).Msg("Failed to get module ID")
		} else if id > 0 {
			moduleID = &id
		}
	}

	entries, err := queries.GetLeaderboard(ctx, sort, order, moduleID, 100)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get leaderboard")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal error"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"leaderboard": entries,
	})
}

func (h *UserHandler) GetRecentActivity(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	activities, err := queries.GetRecentActivity(ctx, 10)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get recent activity")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal error"})
		return
	}

	if activities == nil {
		activities = []queries.RecentActivity{}
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"activities": activities,
	})
}

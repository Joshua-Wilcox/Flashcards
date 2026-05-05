package handler

import (
	"net/http"

	"flashcards-go/internal/config"
)

type PaymentsHandler struct {
	cfg *config.Config
}

func NewPaymentsHandler(cfg *config.Config) *PaymentsHandler {
	return &PaymentsHandler{cfg: cfg}
}

func (h *PaymentsHandler) GitHubSponsor(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"redirect_url": h.cfg.GitHubSponsorsURL,
	})
}

func (h *PaymentsHandler) GitHubStar(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{
		"redirect_url": h.cfg.GitHubRepoURL,
	})
}

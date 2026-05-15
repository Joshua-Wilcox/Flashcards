package handler

import (
	"encoding/json"
	"net/http"

	"flashcards-go/internal/auth"
	"flashcards-go/internal/config"
	"flashcards-go/internal/db/queries"

	"github.com/rs/zerolog/log"
)

type AuthHandler struct {
	cfg *config.Config
}

func NewAuthHandler(cfg *config.Config) *AuthHandler {
	return &AuthHandler{cfg: cfg}
}

func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	state := auth.GenerateState()

	session, _ := auth.GetSession(r)
	session.Values["oauth_state"] = state
	_ = session.Save(r, w)

	url := auth.GetAuthURL(state)
	http.Redirect(w, r, url, http.StatusTemporaryRedirect)
}

func (h *AuthHandler) Callback(w http.ResponseWriter, r *http.Request) {
	code := r.URL.Query().Get("code")
	state := r.URL.Query().Get("state")
	if code == "" {
		http.Error(w, "Missing code parameter", http.StatusBadRequest)
		return
	}

	session, err := auth.GetSession(r)
	if err != nil {
		http.Error(w, "Session error", http.StatusInternalServerError)
		return
	}

	expectedState, _ := session.Values["oauth_state"].(string)
	if expectedState == "" || state != expectedState {
		http.Error(w, "Invalid OAuth state", http.StatusBadRequest)
		return
	}
	delete(session.Values, "oauth_state")

	token, err := auth.ExchangeCode(r.Context(), code)
	if err != nil {
		log.Error().Err(err).Msg("Failed to exchange code")
		http.Error(w, "Failed to exchange code", http.StatusInternalServerError)
		return
	}

	user, err := auth.FetchUser(r.Context(), token)
	if err != nil {
		log.Error().Err(err).Msg("Failed to fetch user")
		http.Error(w, "Failed to fetch user", http.StatusInternalServerError)
		return
	}

	if err := auth.SetSessionValues(w, r, user.ID, user.Username, h.cfg.SessionVersion); err != nil {
		log.Error().Err(err).Msg("Failed to save session")
		http.Error(w, "Failed to save session", http.StatusInternalServerError)
		return
	}

	// Store the OAuth token for later revocation
	if err := auth.SetSessionToken(w, r, token); err != nil {
		log.Warn().Err(err).Msg("Failed to store OAuth token in session")
	}

	_, err = queries.GetOrCreateUserStats(r.Context(), user.ID, user.Username)
	if err != nil {
		log.Error().Err(err).Msg("Failed to create user stats")
	}

	redirectURL := "/"
	if h.cfg.FrontendURL != "" {
		redirectURL = h.cfg.FrontendURL
	}
	http.Redirect(w, r, redirectURL, http.StatusFound)
}

func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	// Get the OAuth token before clearing the session
	token := auth.GetSessionToken(r)
	
	// Revoke the Discord token
	if token != nil {
		if err := auth.RevokeToken(r.Context(), token); err != nil {
			log.Warn().Err(err).Msg("Failed to revoke Discord token")
		}
	}

	if err := auth.ClearSession(w, r); err != nil {
		log.Error().Err(err).Msg("Failed to clear session")
	}
	redirectURL := "/"
	if h.cfg.FrontendURL != "" {
		redirectURL = h.cfg.FrontendURL
	}
	http.Redirect(w, r, redirectURL, http.StatusFound)
}

func (h *AuthHandler) Me(w http.ResponseWriter, r *http.Request) {
	userID := auth.GetUserID(r.Context())
	username := auth.GetUsername(r.Context())
	isAdmin := auth.GetIsAdmin(r.Context())

	if userID == "" {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"authenticated": false,
		})
		return
	}

	isWhitelisted := auth.IsUserWhitelistedCtx(r.Context(), userID)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"authenticated":  true,
		"user_id":        userID,
		"username":       username,
		"is_admin":       isAdmin,
		"is_whitelisted": isWhitelisted,
	})
}

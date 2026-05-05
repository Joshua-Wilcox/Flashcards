package auth

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/gob"
	"net/http"
	"strconv"

	"flashcards-go/internal/config"

	"github.com/gorilla/sessions"
	"golang.org/x/oauth2"
)

type contextKey string

const (
	SessionName           = "flashcards_session"
	UserIDKey   contextKey = "user_id"
	UsernameKey contextKey = "username"
	IsAdminKey  contextKey = "is_admin"
)

var store *sessions.CookieStore

func InitSessions(cfg *config.Config) {
	gob.Register(map[string]interface{}{})
	gob.Register(&oauth2.Token{})
	
	store = sessions.NewCookieStore([]byte(cfg.SecretKey))
	store.Options = &sessions.Options{
		Path:     "/",
		MaxAge:   86400 * 30,
		HttpOnly: true,
		Secure:   !cfg.IsTesting,
		SameSite: http.SameSiteLaxMode,
		Domain:   "", // Empty allows the cookie to work on any domain/port on localhost
	}
}

func GetSession(r *http.Request) (*sessions.Session, error) {
	return store.Get(r, SessionName)
}

func SetSessionValues(w http.ResponseWriter, r *http.Request, userID, username string, sessionVersion int) error {
	session, err := GetSession(r)
	if err != nil {
		return err
	}

	session.Values["user_id"] = userID
	session.Values["username"] = username
	session.Values["session_version"] = sessionVersion

	return session.Save(r, w)
}

func SetSessionToken(w http.ResponseWriter, r *http.Request, token *oauth2.Token) error {
	session, err := GetSession(r)
	if err != nil {
		return err
	}

	session.Values["oauth_token"] = token
	return session.Save(r, w)
}

func GetSessionToken(r *http.Request) *oauth2.Token {
	session, err := GetSession(r)
	if err != nil {
		return nil
	}

	if token, ok := session.Values["oauth_token"].(*oauth2.Token); ok {
		return token
	}
	return nil
}

func ClearSession(w http.ResponseWriter, r *http.Request) error {
	session, err := GetSession(r)
	if err != nil {
		return err
	}

	session.Values = make(map[interface{}]interface{})
	session.Options.MaxAge = -1

	return session.Save(r, w)
}

func GenerateState() string {
	b := make([]byte, 32)
	rand.Read(b)
	return base64.URLEncoding.EncodeToString(b)
}

func RequireAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		session, err := GetSession(r)
		if err != nil {
			http.Error(w, "Session error", http.StatusInternalServerError)
			return
		}

		userID, ok := session.Values["user_id"].(string)
		if !ok || userID == "" {
			http.Error(w, `{"error": "Please log in to access flashcards."}`, http.StatusUnauthorized)
			return
		}

		username, _ := session.Values["username"].(string)

		userIDInt, _ := strconv.ParseInt(userID, 10, 64)
		isAdmin := IsUserAdmin(userIDInt)

		ctx := context.WithValue(r.Context(), UserIDKey, userID)
		ctx = context.WithValue(ctx, UsernameKey, username)
		ctx = context.WithValue(ctx, IsAdminKey, isAdmin)

		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func RequireAdmin(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		session, err := GetSession(r)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte(`{"error": "Session error"}`))
			return
		}

		userID, ok := session.Values["user_id"].(string)
		if !ok || userID == "" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			w.Write([]byte(`{"error": "Please log in to access this resource."}`))
			return
		}

		userIDInt, _ := strconv.ParseInt(userID, 10, 64)
		if !IsUserAdmin(userIDInt) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			w.Write([]byte(`{"error": "Admin access required."}`))
			return
		}

		username, _ := session.Values["username"].(string)

		ctx := context.WithValue(r.Context(), UserIDKey, userID)
		ctx = context.WithValue(ctx, UsernameKey, username)
		ctx = context.WithValue(ctx, IsAdminKey, true)

		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func OptionalAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		session, err := GetSession(r)
		if err != nil {
			next.ServeHTTP(w, r)
			return
		}

		userID, ok := session.Values["user_id"].(string)
		if ok && userID != "" {
			username, _ := session.Values["username"].(string)
			userIDInt, _ := strconv.ParseInt(userID, 10, 64)
			isAdmin := IsUserAdmin(userIDInt)

			ctx := context.WithValue(r.Context(), UserIDKey, userID)
			ctx = context.WithValue(ctx, UsernameKey, username)
			ctx = context.WithValue(ctx, IsAdminKey, isAdmin)
			r = r.WithContext(ctx)
		}

		next.ServeHTTP(w, r)
	})
}

func GetUserID(ctx context.Context) string {
	if v := ctx.Value(UserIDKey); v != nil {
		return v.(string)
	}
	return ""
}

func GetUsername(ctx context.Context) string {
	if v := ctx.Value(UsernameKey); v != nil {
		return v.(string)
	}
	return ""
}

func GetIsAdmin(ctx context.Context) bool {
	if v := ctx.Value(IsAdminKey); v != nil {
		return v.(bool)
	}
	return false
}

func EnforceSessionVersion(cfg *config.Config) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			session, err := GetSession(r)
			if err != nil {
				next.ServeHTTP(w, r)
				return
			}

			version, ok := session.Values["session_version"].(int)
			if !ok || version != cfg.SessionVersion {
				session.Values = make(map[interface{}]interface{})
				session.Values["session_version"] = cfg.SessionVersion
				session.Save(r, w)
			}

			next.ServeHTTP(w, r)
		})
	}
}

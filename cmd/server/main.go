package main

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"flashcards-go/internal/auth"
	"flashcards-go/internal/config"
	"flashcards-go/internal/db"
	"flashcards-go/internal/security"

	"github.com/joho/godotenv"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
)

func main() {
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix
	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})

	envPaths := []string{".env", "../.env", "../../.env", "../../../.env"}
	loaded := false
	for _, path := range envPaths {
		if err := godotenv.Load(path); err == nil {
			log.Info().Str("path", path).Msg("Loaded .env file")
			loaded = true
			break
		}
	}
	if !loaded {
		log.Warn().Msg("No .env file found, using environment variables")
	}

	cfg := config.Load()

	security.Init(cfg.TokenSecretKey)
	security.SetTokenExpiry(cfg.TokenExpirySeconds)
	security.StartCacheCleanup(5*time.Minute, 15*time.Minute)
	security.StartQueueCleanup(5 * time.Minute)
	auth.Init(cfg)
	auth.InitSessions(cfg)

	whitelistPaths := []string{"whitelist.json", "../whitelist.json", "../../whitelist.json"}
	whitelistLoaded := false
	for _, p := range whitelistPaths {
		if err := auth.LoadWhitelist(p); err == nil {
			log.Info().Str("path", p).Msg("Loaded whitelist")
			whitelistLoaded = true
			break
		}
	}
	if !whitelistLoaded {
		log.Warn().Msg("Could not load whitelist.json from any known location")
	}

	if err := db.Connect(cfg.DatabaseURL); err != nil {
		log.Fatal().Err(err).Msg("Failed to connect to database")
	}
	defer db.Close()

	router := setupRouter(cfg)

	server := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Info().Str("port", cfg.Port).Msg("Starting server")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal().Err(err).Msg("Server failed")
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Info().Msg("Shutting down server...")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Fatal().Err(err).Msg("Server forced to shutdown")
	}

	log.Info().Msg("Server exited")
}

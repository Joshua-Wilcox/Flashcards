package config

import (
	"os"
	"strconv"
)

type Config struct {
	// Flask equivalent
	SecretKey string
	IsTesting bool

	// Discord OAuth
	DiscordClientID     string
	DiscordClientSecret string
	DiscordRedirectURI  string

	// Supabase
	SupabaseURL            string
	SupabaseAnonKey        string
	SupabaseServiceRoleKey string
	DatabaseURL            string

	// Application constants
	SessionVersion     int
	NumberOfDistractors int

	// Security
	TokenSecretKey     string
	TokenExpirySeconds int

	// GitHub
	GitHubSponsorsURL string
	GitHubRepoURL     string

	// n8n ingestion
	N8NIngestToken    string
	N8NDefaultUserID  string
	N8NDefaultUsername string

	// Server
	Port        string
	FrontendURL string
}

func Load() *Config {
	isTesting := os.Getenv("IS_TESTING")
	isTestingBool := isTesting == "yes" || isTesting == "true" || isTesting == "1"

	var discordClientID, discordClientSecret, discordRedirectURI string
	if isTestingBool {
		discordClientID = os.Getenv("TEST_CLIENT_ID")
		discordClientSecret = os.Getenv("TEST_SECRET")
		discordRedirectURI = getEnvOrDefault("TEST_REDIRECT_URI", "http://127.0.0.1:2456/callback")
	} else {
		discordClientID = os.Getenv("DISCORD_CLIENT_ID")
		discordClientSecret = os.Getenv("DISCORD_CLIENT_SECRET")
		discordRedirectURI = os.Getenv("DISCORD_REDIRECT_URI")
	}

	frontendURL := getEnvOrDefault("FRONTEND_URL", "")
	if frontendURL == "" && isTestingBool {
		frontendURL = "http://localhost:3000"
	}

	sessionVersion, _ := strconv.Atoi(getEnvOrDefault("SESSION_VERSION", "4"))
	numberOfDistractors, _ := strconv.Atoi(getEnvOrDefault("NUMBER_OF_DISTRACTORS", "4"))
	tokenExpirySeconds, _ := strconv.Atoi(getEnvOrDefault("TOKEN_EXPIRY_SECONDS", "600"))

	return &Config{
		SecretKey: getEnvOrDefault("SECRET_KEY", "dev_secret_key"),
		IsTesting: isTestingBool,

		DiscordClientID:     discordClientID,
		DiscordClientSecret: discordClientSecret,
		DiscordRedirectURI:  discordRedirectURI,

		SupabaseURL:            os.Getenv("SUPABASE_URL"),
		SupabaseAnonKey:        os.Getenv("SUPABASE_ANON_KEY"),
		SupabaseServiceRoleKey: os.Getenv("SUPABASE_SERVICE_ROLE_KEY"),
		DatabaseURL:            os.Getenv("DATABASE_URL"),

		SessionVersion:      sessionVersion,
		NumberOfDistractors: numberOfDistractors,

		TokenSecretKey:     getEnvOrDefault("TOKEN_SECRET_KEY", "dev_token_secret"),
		TokenExpirySeconds: tokenExpirySeconds,

		GitHubSponsorsURL: "https://github.com/sponsors/Joshua-Wilcox?o=esb",
		GitHubRepoURL:     "https://github.com/Joshua-Wilcox/Flashcards",

		N8NIngestToken:     os.Getenv("N8N_INGEST_TOKEN"),
		N8NDefaultUserID:   getEnvOrDefault("N8N_DEFAULT_USER_ID", "n8n-ingest"),
		N8NDefaultUsername: getEnvOrDefault("N8N_DEFAULT_USERNAME", "n8n-bot"),

		Port:        getEnvOrDefault("PORT", "2456"),
		FrontendURL: frontendURL,
	}
}

func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

package auth

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"flashcards-go/internal/config"

	"github.com/rs/zerolog/log"
	"golang.org/x/oauth2"
)

var (
	discordOAuthConfig *oauth2.Config
	cfg                *config.Config
)

type DiscordUser struct {
	ID            string `json:"id"`
	Username      string `json:"username"`
	Discriminator string `json:"discriminator"`
	Avatar        string `json:"avatar"`
	Email         string `json:"email,omitempty"`
}

func Init(c *config.Config) {
	cfg = c
	discordOAuthConfig = &oauth2.Config{
		ClientID:     c.DiscordClientID,
		ClientSecret: c.DiscordClientSecret,
		RedirectURL:  c.DiscordRedirectURI,
		Scopes:       []string{"identify"},
		Endpoint: oauth2.Endpoint{
			AuthURL:  "https://discord.com/api/oauth2/authorize",
			TokenURL: "https://discord.com/api/oauth2/token",
		},
	}
}

func GetAuthURL(state string) string {
	return discordOAuthConfig.AuthCodeURL(state, oauth2.AccessTypeOnline)
}

func ExchangeCode(ctx context.Context, code string) (*oauth2.Token, error) {
	return discordOAuthConfig.Exchange(ctx, code)
}

func FetchUser(ctx context.Context, token *oauth2.Token) (*DiscordUser, error) {
	client := discordOAuthConfig.Client(ctx, token)
	
	resp, err := client.Get("https://discord.com/api/users/@me")
	if err != nil {
		return nil, fmt.Errorf("failed to fetch user: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("discord API returned status %d", resp.StatusCode)
	}

	var user DiscordUser
	if err := json.NewDecoder(resp.Body).Decode(&user); err != nil {
		return nil, fmt.Errorf("failed to decode user: %w", err)
	}

	return &user, nil
}

// RevokeToken revokes the Discord OAuth token
// This invalidates both the access token and refresh token
func RevokeToken(ctx context.Context, token *oauth2.Token) error {
	if token == nil || token.AccessToken == "" {
		return nil
	}

	if cfg == nil || cfg.DiscordClientID == "" || cfg.DiscordClientSecret == "" {
		log.Warn().Msg("Discord credentials not configured, skipping token revocation")
		return nil
	}

	data := url.Values{}
	data.Set("token", token.AccessToken)
	data.Set("token_type_hint", "access_token")

	req, err := http.NewRequestWithContext(ctx, "POST",
		"https://discord.com/api/oauth2/token/revoke",
		strings.NewReader(data.Encode()))
	if err != nil {
		return fmt.Errorf("failed to create revoke request: %w", err)
	}

	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.SetBasicAuth(cfg.DiscordClientID, cfg.DiscordClientSecret)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to revoke token: %w", err)
	}
	defer resp.Body.Close()

	// Discord returns 200 on success, but we don't fail on other status codes
	// since the token might already be invalid
	if resp.StatusCode != http.StatusOK {
		log.Warn().Int("status", resp.StatusCode).Msg("Discord token revocation returned non-200")
	} else {
		log.Debug().Msg("Discord token revoked successfully")
	}

	return nil
}

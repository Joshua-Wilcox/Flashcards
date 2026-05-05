package auth

import (
	"encoding/json"
	"os"
	"sync"

	"github.com/rs/zerolog/log"
)

type Whitelist struct {
	UserIDs  []int64 `json:"user_ids"`
	GuildIDs []int64 `json:"guild_ids,omitempty"`
	AdminIDs []int64 `json:"admin_ids"`
}

var (
	whitelist     *Whitelist
	whitelistLock sync.RWMutex
)

func LoadWhitelist(path string) error {
	whitelistLock.Lock()
	defer whitelistLock.Unlock()

	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			whitelist = &Whitelist{
				UserIDs:  []int64{},
				AdminIDs: []int64{},
			}
			log.Warn().Str("path", path).Msg("Whitelist file not found, using empty whitelist")
			return nil
		}
		return err
	}

	var wl Whitelist
	if err := json.Unmarshal(data, &wl); err != nil {
		return err
	}

	whitelist = &wl
	log.Info().Int("users", len(wl.UserIDs)).Int("admins", len(wl.AdminIDs)).Msg("Whitelist loaded")
	return nil
}

func IsUserWhitelisted(userID int64) bool {
	whitelistLock.RLock()
	defer whitelistLock.RUnlock()

	if whitelist == nil {
		return false
	}

	for _, id := range whitelist.UserIDs {
		if id == userID {
			return true
		}
	}
	return false
}

func IsUserAdmin(userID int64) bool {
	whitelistLock.RLock()
	defer whitelistLock.RUnlock()

	if whitelist == nil {
		return false
	}

	for _, id := range whitelist.AdminIDs {
		if id == userID {
			return true
		}
	}
	return false
}

func AddUserToWhitelist(userID int64, path string) error {
	whitelistLock.Lock()
	defer whitelistLock.Unlock()

	if whitelist == nil {
		whitelist = &Whitelist{
			UserIDs:  []int64{},
			AdminIDs: []int64{},
		}
	}

	for _, id := range whitelist.UserIDs {
		if id == userID {
			return nil
		}
	}

	whitelist.UserIDs = append(whitelist.UserIDs, userID)

	data, err := json.MarshalIndent(whitelist, "", "  ")
	if err != nil {
		return err
	}

	return os.WriteFile(path, data, 0644)
}

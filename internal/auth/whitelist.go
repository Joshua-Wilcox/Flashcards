package auth

import (
	"context"

	"flashcards-go/internal/db/queries"
)

func IsUserAdminCtx(ctx context.Context, userID string) bool {
	isAdmin, err := queries.IsUserAdmin(ctx, userID)
	if err != nil {
		return false
	}
	return isAdmin
}

func IsUserWhitelistedCtx(ctx context.Context, userID string) bool {
	has, err := queries.HasPDFAccess(ctx, userID)
	if err != nil {
		return false
	}
	return has
}

func GrantPDFAccess(ctx context.Context, userID string) error {
	return queries.GrantPDFAccess(ctx, userID)
}

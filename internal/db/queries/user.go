package queries

import (
	"context"
	"time"

	"flashcards-go/internal/db"

	"github.com/jackc/pgx/v5"
)

type UserStats struct {
	UserID         string     `json:"user_id"`
	Username       string     `json:"username"`
	CorrectAnswers int        `json:"correct_answers"`
	TotalAnswers   int        `json:"total_answers"`
	CurrentStreak  int        `json:"current_streak"`
	MaxStreak      int        `json:"max_streak"`
	ApprovedCards  int        `json:"approved_cards"`
	LastAnswerTime *time.Time `json:"last_answer_time,omitempty"`
}

type ModuleStats struct {
	ModuleID       int        `json:"module_id"`
	ModuleName     string     `json:"module_name,omitempty"`
	NumberAnswered int        `json:"number_answered"`
	NumberCorrect  int        `json:"number_correct"`
	CurrentStreak  int        `json:"current_streak"`
	ApprovedCards  int        `json:"approved_cards"`
	LastAnsweredTime *time.Time `json:"last_answered_time,omitempty"`
}

func GetUserStats(ctx context.Context, userID string) (*UserStats, error) {
	var stats UserStats
	err := db.Pool.QueryRow(ctx, `
		SELECT user_id, username, correct_answers, total_answers,
		       current_streak, COALESCE(max_streak, 0), approved_cards, last_answer_time
		FROM user_stats
		WHERE user_id = $1
	`, userID).Scan(
		&stats.UserID, &stats.Username, &stats.CorrectAnswers,
		&stats.TotalAnswers, &stats.CurrentStreak, &stats.MaxStreak, &stats.ApprovedCards,
		&stats.LastAnswerTime,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &stats, nil
}

func GetOrCreateUserStats(ctx context.Context, userID, username string) (*UserStats, error) {
	stats, err := GetUserStats(ctx, userID)
	if err != nil {
		return nil, err
	}
	if stats != nil {
		return stats, nil
	}

	_, err = db.Pool.Exec(ctx, `
		INSERT INTO user_stats (user_id, username, correct_answers, total_answers, current_streak, max_streak, approved_cards)
		VALUES ($1, $2, 0, 0, 0, 0, 0)
		ON CONFLICT (user_id) DO NOTHING
	`, userID, username)
	if err != nil {
		return nil, err
	}

	return GetUserStats(ctx, userID)
}

func GetUserModuleStats(ctx context.Context, userID string) ([]ModuleStats, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT ms.module_id, m.name, ms.number_answered, ms.number_correct,
		       ms.current_streak, ms.approved_cards, ms.last_answered_time
		FROM module_stats ms
		JOIN modules m ON ms.module_id = m.id
		WHERE ms.user_id = $1
		ORDER BY m.name
	`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var stats []ModuleStats
	for rows.Next() {
		var s ModuleStats
		if err := rows.Scan(&s.ModuleID, &s.ModuleName, &s.NumberAnswered,
			&s.NumberCorrect, &s.CurrentStreak, &s.ApprovedCards, &s.LastAnsweredTime); err != nil {
			return nil, err
		}
		stats = append(stats, s)
	}
	return stats, rows.Err()
}

type LeaderboardEntry struct {
	UserID         string     `json:"user_id"`
	Username       string     `json:"username"`
	CorrectAnswers int        `json:"correct_answers"`
	TotalAnswers   int        `json:"total_answers"`
	CurrentStreak  int        `json:"current_streak"`
	MaxStreak      int        `json:"max_streak"`
	ApprovedCards  int        `json:"approved_cards"`
	LastAnswerTime *time.Time `json:"last_answer_time,omitempty"`
}

func GetLeaderboard(ctx context.Context, sortBy, order string, moduleID *int, limit int) ([]LeaderboardEntry, error) {
	// Map sort field names to SQL expressions
	sortExpressions := map[string]string{
		"correct_answers": "correct_answers",
		"total_answers":   "total_answers",
		"current_streak":  "current_streak",
		"max_streak":      "max_streak",
		"approved_cards":  "approved_cards",
		"accuracy":        "(CASE WHEN total_answers > 0 THEN correct_answers::float / total_answers ELSE 0 END)",
		"last_answer_time": "last_answer_time",
	}
	sortExpr, valid := sortExpressions[sortBy]
	if !valid {
		sortExpr = "correct_answers"
	}
	if order != "asc" && order != "desc" {
		order = "desc"
	}

	var query string
	var args []interface{}

	nullsClause := ""
	if sortBy == "last_answer_time" {
		if order == "desc" {
			nullsClause = " NULLS LAST"
		} else {
			nullsClause = " NULLS LAST"
		}
	}

	if moduleID != nil {
		query = `
			SELECT us.user_id, us.username,
			       COALESCE(ms.number_correct, 0) as correct_answers,
			       COALESCE(ms.number_answered, 0) as total_answers,
			       COALESCE(ms.current_streak, 0) as current_streak,
			       COALESCE(us.max_streak, 0) as max_streak,
			       COALESCE(ms.approved_cards, 0) as approved_cards,
			       us.last_answer_time
			FROM user_stats us
			LEFT JOIN module_stats ms ON us.user_id = ms.user_id AND ms.module_id = $1
			WHERE ms.number_answered > 0
			ORDER BY ` + sortExpr + ` ` + order + nullsClause + `
			LIMIT $2
		`
		args = []interface{}{*moduleID, limit}
	} else {
		query = `
			SELECT user_id, username, correct_answers, total_answers,
			       current_streak, COALESCE(max_streak, 0), approved_cards, last_answer_time
			FROM user_stats
			WHERE total_answers > 0
			ORDER BY ` + sortExpr + ` ` + order + nullsClause + `
			LIMIT $1
		`
		args = []interface{}{limit}
	}

	rows, err := db.Pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var entries []LeaderboardEntry
	for rows.Next() {
		var e LeaderboardEntry
		if err := rows.Scan(&e.UserID, &e.Username, &e.CorrectAnswers,
			&e.TotalAnswers, &e.CurrentStreak, &e.MaxStreak, &e.ApprovedCards, &e.LastAnswerTime); err != nil {
			return nil, err
		}
		entries = append(entries, e)
	}
	return entries, rows.Err()
}

func IsTokenUsed(ctx context.Context, userID, token string) (bool, error) {
	var exists bool
	err := db.Pool.QueryRow(ctx, `
		SELECT EXISTS(SELECT 1 FROM used_tokens WHERE user_id = $1 AND token = $2)
	`, userID, token).Scan(&exists)
	return exists, err
}

func MarkTokenUsed(ctx context.Context, userID, token string) error {
	_, err := db.Pool.Exec(ctx, `
		INSERT INTO used_tokens (user_id, token) VALUES ($1, $2)
	`, userID, token)
	return err
}

func ResetUserStreak(ctx context.Context, userID string, moduleID int) error {
	// Reset global streak
	_, err := db.Pool.Exec(ctx, `
		UPDATE user_stats SET current_streak = 0 WHERE user_id = $1
	`, userID)
	if err != nil {
		return err
	}
	
	// Reset module streak
	_, err = db.Pool.Exec(ctx, `
		UPDATE module_stats SET current_streak = 0 WHERE user_id = $1 AND module_id = $2
	`, userID, moduleID)
	return err
}

type AnswerResult struct {
	Correct       bool `json:"correct"`
	NewStreak     int  `json:"new_streak"`
	MaxStreak     int  `json:"max_streak"`
	TotalCorrect  int  `json:"total_correct"`
	TotalAnswers  int  `json:"total_answers"`
	ModuleStreak  int  `json:"module_streak"`
	ModuleCorrect int  `json:"module_correct"`
	ModuleAnswers int  `json:"module_answers"`
}

func ProcessAnswerCheck(ctx context.Context, userID, questionID, submittedAnswer, token, username string) (*AnswerResult, string, error) {
	tx, err := db.Pool.Begin(ctx)
	if err != nil {
		return nil, "", err
	}
	defer tx.Rollback(ctx)

	var tokenUsed bool
	err = tx.QueryRow(ctx, `
		SELECT EXISTS(SELECT 1 FROM used_tokens WHERE user_id = $1 AND token = $2)
	`, userID, token).Scan(&tokenUsed)
	if err != nil {
		return nil, "", err
	}
	if tokenUsed {
		return nil, "Token already used", nil
	}

	var correctAnswer string
	var moduleID int
	err = tx.QueryRow(ctx, `
		SELECT answer, module_id FROM questions WHERE id = $1
	`, questionID).Scan(&correctAnswer, &moduleID)
	if err == pgx.ErrNoRows {
		return nil, "Question not found", nil
	}
	if err != nil {
		return nil, "", err
	}

	isCorrect := submittedAnswer == correctAnswer
	now := time.Now()

	var currentCorrect, currentTotal, currentStreak, currentMaxStreak int
	err = tx.QueryRow(ctx, `
		SELECT COALESCE(correct_answers, 0), COALESCE(total_answers, 0), COALESCE(current_streak, 0), COALESCE(max_streak, 0)
		FROM user_stats WHERE user_id = $1
	`, userID).Scan(&currentCorrect, &currentTotal, &currentStreak, &currentMaxStreak)
	if err == pgx.ErrNoRows {
		currentCorrect, currentTotal, currentStreak, currentMaxStreak = 0, 0, 0, 0
	} else if err != nil {
		return nil, "", err
	}

	newCorrect := currentCorrect
	newTotal := currentTotal + 1
	newStreak := 0
	if isCorrect {
		newCorrect++
		newStreak = currentStreak + 1
	}
	newMaxStreak := currentMaxStreak
	if newStreak > newMaxStreak {
		newMaxStreak = newStreak
	}

	_, err = tx.Exec(ctx, `
		INSERT INTO user_stats (user_id, username, correct_answers, total_answers, current_streak, max_streak, last_answer_time)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		ON CONFLICT (user_id) DO UPDATE SET
			correct_answers = EXCLUDED.correct_answers,
			total_answers = EXCLUDED.total_answers,
			current_streak = EXCLUDED.current_streak,
			max_streak = EXCLUDED.max_streak,
			last_answer_time = EXCLUDED.last_answer_time,
			username = EXCLUDED.username
	`, userID, username, newCorrect, newTotal, newStreak, newMaxStreak, now)
	if err != nil {
		return nil, "", err
	}

	var moduleCorrect, moduleAnswered, moduleStreak int
	err = tx.QueryRow(ctx, `
		SELECT COALESCE(number_correct, 0), COALESCE(number_answered, 0), COALESCE(current_streak, 0)
		FROM module_stats WHERE user_id = $1 AND module_id = $2
	`, userID, moduleID).Scan(&moduleCorrect, &moduleAnswered, &moduleStreak)
	if err == pgx.ErrNoRows {
		moduleCorrect, moduleAnswered, moduleStreak = 0, 0, 0
	} else if err != nil {
		return nil, "", err
	}

	newModuleAnswered := moduleAnswered + 1
	newModuleCorrect := moduleCorrect
	newModuleStreak := 0
	if isCorrect {
		newModuleCorrect++
		newModuleStreak = moduleStreak + 1
	}

	_, err = tx.Exec(ctx, `
		INSERT INTO module_stats (user_id, module_id, number_answered, number_correct, current_streak, last_answered_time)
		VALUES ($1, $2, $3, $4, $5, $6)
		ON CONFLICT (user_id, module_id) DO UPDATE SET
			number_answered = EXCLUDED.number_answered,
			number_correct = EXCLUDED.number_correct,
			current_streak = EXCLUDED.current_streak,
			last_answered_time = EXCLUDED.last_answered_time
	`, userID, moduleID, newModuleAnswered, newModuleCorrect, newModuleStreak, now)
	if err != nil {
		return nil, "", err
	}

	if isCorrect {
		_, err = tx.Exec(ctx, `
			INSERT INTO used_tokens (user_id, token) VALUES ($1, $2)
		`, userID, token)
		if err != nil {
			return nil, "", err
		}

		var moduleName string
		err = tx.QueryRow(ctx, `SELECT name FROM modules WHERE id = $1`, moduleID).Scan(&moduleName)
		if err != nil {
			return nil, "", err
		}

		_, err = tx.Exec(ctx, `
			INSERT INTO live_activity_logs (user_id, username, module_name, streak, answered_at)
			VALUES ($1, $2, $3, $4, $5)
			ON CONFLICT (user_id) DO UPDATE SET
				username = EXCLUDED.username,
				module_name = EXCLUDED.module_name,
				streak = EXCLUDED.streak,
				answered_at = EXCLUDED.answered_at
		`, userID, username, moduleName, newStreak, now)
		if err != nil {
			return nil, "", err
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, "", err
	}

	return &AnswerResult{
		Correct:       isCorrect,
		NewStreak:     newStreak,
		MaxStreak:     newMaxStreak,
		TotalCorrect:  newCorrect,
		TotalAnswers:  newTotal,
		ModuleStreak:  newModuleStreak,
		ModuleCorrect: newModuleCorrect,
		ModuleAnswers: newModuleAnswered,
	}, "", nil
}

type RecentActivity struct {
	UserID     string `json:"user_id"`
	Username   string `json:"username"`
	ModuleName string `json:"module_name"`
	Streak     int    `json:"streak"`
	AnsweredAt string `json:"answered_at"`
}

func GetRecentActivity(ctx context.Context, limit int) ([]RecentActivity, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT user_id, username, module_name, streak, answered_at
		FROM live_activity_logs
		ORDER BY answered_at DESC
		LIMIT $1
	`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var activities []RecentActivity
	for rows.Next() {
		var a RecentActivity
		var answeredAt time.Time
		if err := rows.Scan(&a.UserID, &a.Username, &a.ModuleName, &a.Streak, &answeredAt); err != nil {
			return nil, err
		}
		a.AnsweredAt = answeredAt.Format(time.RFC3339)
		activities = append(activities, a)
	}
	return activities, rows.Err()
}

package handler

import (
	"context"

	"flashcards-go/internal/db"
	"flashcards-go/internal/duplicate"
)

func FindDuplicates(ctx context.Context, question string, moduleID int, threshold float64) []map[string]interface{} {
	rows, err := db.Pool.Query(ctx, `
		SELECT id, question, answer FROM questions WHERE module_id = $1
	`, moduleID)
	if err != nil {
		return nil
	}
	defer rows.Close()

	var docs []duplicate.Document
	for rows.Next() {
		var d duplicate.Document
		if err := rows.Scan(&d.ID, &d.Question, &d.Answer); err != nil {
			continue
		}
		docs = append(docs, d)
	}

	matches := duplicate.FindSemanticDuplicates(question, docs, threshold, 5)

	var result []map[string]interface{}
	for _, m := range matches {
		result = append(result, map[string]interface{}{
			"reason":     "semantic-match",
			"id":         m.ID,
			"question":   m.Question,
			"answer":     m.Answer,
			"similarity": m.Similarity,
		})
	}

	return result
}

package queries

import (
	"context"

	"flashcards-go/internal/db"

	"github.com/jackc/pgx/v5"
)

type Question struct {
	ID        string   `json:"id"`
	Question  string   `json:"question"`
	Answer    string   `json:"answer"`
	ModuleID  int      `json:"module_id"`
	Topics    []string `json:"topics"`
	Subtopics []string `json:"subtopics"`
	Tags      []string `json:"tags"`
}

type Distractor struct {
	ID       string `json:"id"`
	Answer   string `json:"answer"`
	Type     string `json:"type"`
	Metadata *int   `json:"metadata,omitempty"`
}

func GetRandomQuestion(ctx context.Context, moduleID int, topics, subtopics, tags []string, specificQuestionID string) (*Question, error) {
	query := `
		WITH filtered_questions AS (
			SELECT DISTINCT q.id, q.question, q.answer, q.module_id
			FROM questions q
			LEFT JOIN question_topics qt ON q.id = qt.question_id
			LEFT JOIN topics t ON qt.topic_id = t.id
			LEFT JOIN question_subtopics qst ON q.id = qst.question_id
			LEFT JOIN subtopics st ON qst.subtopic_id = st.id
			LEFT JOIN question_tags qtag ON q.id = qtag.question_id
			LEFT JOIN tags tag ON qtag.tag_id = tag.id
			WHERE q.module_id = $1
			  AND ($2::text IS NULL OR q.id = $2)
			  AND ($3::text[] IS NULL OR array_length($3::text[], 1) IS NULL OR t.name = ANY($3))
			  AND ($4::text[] IS NULL OR array_length($4::text[], 1) IS NULL OR st.name = ANY($4))
			  AND ($5::text[] IS NULL OR array_length($5::text[], 1) IS NULL OR tag.name = ANY($5))
		)
		SELECT id, question, answer, module_id
		FROM filtered_questions
		ORDER BY random()
		LIMIT 1
	`

	var specificID *string
	if specificQuestionID != "" {
		specificID = &specificQuestionID
	}

	var topicsParam, subtopicsParam, tagsParam interface{}
	if len(topics) > 0 {
		topicsParam = topics
	}
	if len(subtopics) > 0 {
		subtopicsParam = subtopics
	}
	if len(tags) > 0 {
		tagsParam = tags
	}

	var q Question
	err := db.Pool.QueryRow(ctx, query, moduleID, specificID, topicsParam, subtopicsParam, tagsParam).
		Scan(&q.ID, &q.Question, &q.Answer, &q.ModuleID)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	q.Topics, q.Subtopics, q.Tags, err = GetQuestionMetadata(ctx, q.ID)
	if err != nil {
		return nil, err
	}

	return &q, nil
}

func GetQuestionMetadata(ctx context.Context, questionID string) (topics, subtopics, tags []string, err error) {
	topicsQuery := `
		SELECT t.name FROM topics t
		JOIN question_topics qt ON t.id = qt.topic_id
		WHERE qt.question_id = $1
		ORDER BY t.name
	`
	rows, err := db.Pool.Query(ctx, topicsQuery, questionID)
	if err != nil {
		return nil, nil, nil, err
	}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			rows.Close()
			return nil, nil, nil, err
		}
		topics = append(topics, name)
	}
	rows.Close()

	subtopicsQuery := `
		SELECT st.name FROM subtopics st
		JOIN question_subtopics qst ON st.id = qst.subtopic_id
		WHERE qst.question_id = $1
		ORDER BY st.name
	`
	rows, err = db.Pool.Query(ctx, subtopicsQuery, questionID)
	if err != nil {
		return nil, nil, nil, err
	}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			rows.Close()
			return nil, nil, nil, err
		}
		subtopics = append(subtopics, name)
	}
	rows.Close()

	tagsQuery := `
		SELECT tag.name FROM tags tag
		JOIN question_tags qtag ON tag.id = qtag.tag_id
		WHERE qtag.question_id = $1
		ORDER BY tag.name
	`
	rows, err = db.Pool.Query(ctx, tagsQuery, questionID)
	if err != nil {
		return nil, nil, nil, err
	}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			rows.Close()
			return nil, nil, nil, err
		}
		tags = append(tags, name)
	}
	rows.Close()

	return topics, subtopics, tags, nil
}

func GetQuestionByID(ctx context.Context, questionID string) (*Question, error) {
	var q Question
	err := db.Pool.QueryRow(ctx, `
		SELECT id, question, answer, module_id
		FROM questions
		WHERE id = $1
	`, questionID).Scan(&q.ID, &q.Question, &q.Answer, &q.ModuleID)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &q, nil
}

func GetModuleNameByID(ctx context.Context, moduleID int) (string, error) {
	var name string
	err := db.Pool.QueryRow(ctx, `SELECT name FROM modules WHERE id = $1`, moduleID).Scan(&name)
	if err == pgx.ErrNoRows {
		return "", nil
	}
	return name, err
}

func GetRandomQuestionExcluding(ctx context.Context, moduleID int, topics, subtopics, tags []string, specificQuestionID string, excludeIDs []string) (*Question, error) {
	query := `
		WITH filtered_questions AS (
			SELECT DISTINCT q.id, q.question, q.answer, q.module_id
			FROM questions q
			LEFT JOIN question_topics qt ON q.id = qt.question_id
			LEFT JOIN topics t ON qt.topic_id = t.id
			LEFT JOIN question_subtopics qst ON q.id = qst.question_id
			LEFT JOIN subtopics st ON qst.subtopic_id = st.id
			LEFT JOIN question_tags qtag ON q.id = qtag.question_id
			LEFT JOIN tags tag ON qtag.tag_id = tag.id
			WHERE q.module_id = $1
			  AND ($2::text IS NULL OR q.id = $2)
			  AND ($3::text[] IS NULL OR array_length($3::text[], 1) IS NULL OR t.name = ANY($3))
			  AND ($4::text[] IS NULL OR array_length($4::text[], 1) IS NULL OR st.name = ANY($4))
			  AND ($5::text[] IS NULL OR array_length($5::text[], 1) IS NULL OR tag.name = ANY($5))
			  AND ($6::text[] IS NULL OR array_length($6::text[], 1) IS NULL OR q.id != ALL($6))
		)
		SELECT id, question, answer, module_id
		FROM filtered_questions
		ORDER BY random()
		LIMIT 1
	`

	var specificID *string
	if specificQuestionID != "" {
		specificID = &specificQuestionID
	}

	var topicsParam, subtopicsParam, tagsParam, excludeParam interface{}
	if len(topics) > 0 {
		topicsParam = topics
	}
	if len(subtopics) > 0 {
		subtopicsParam = subtopics
	}
	if len(tags) > 0 {
		tagsParam = tags
	}
	if len(excludeIDs) > 0 {
		excludeParam = excludeIDs
	}

	var q Question
	err := db.Pool.QueryRow(ctx, query, moduleID, specificID, topicsParam, subtopicsParam, tagsParam, excludeParam).
		Scan(&q.ID, &q.Question, &q.Answer, &q.ModuleID)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	q.Topics, q.Subtopics, q.Tags, err = GetQuestionMetadata(ctx, q.ID)
	if err != nil {
		return nil, err
	}

	return &q, nil
}

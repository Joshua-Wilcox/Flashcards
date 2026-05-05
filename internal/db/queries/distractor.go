package queries

import (
	"context"

	"flashcards-go/internal/db"
)

func GetManualDistractors(ctx context.Context, questionID string, limit int) ([]Distractor, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT id, distractor_text
		FROM manual_distractors
		WHERE question_id = $1
		LIMIT $2
	`, questionID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var distractors []Distractor
	for rows.Next() {
		var d Distractor
		var id int
		if err := rows.Scan(&id, &d.Answer); err != nil {
			return nil, err
		}
		d.Type = "manual_distractor"
		d.Metadata = &id
		distractors = append(distractors, d)
	}
	return distractors, rows.Err()
}

func GetSmartDistractors(ctx context.Context, questionID string, moduleID int, questionTopics, questionSubtopics, questionTags []string, limit int) ([]Distractor, error) {
	query := `
		SELECT 
			q.id,
			q.answer,
			(
				COALESCE((
					SELECT COUNT(*) FROM question_topics qt2
					JOIN topics t2 ON qt2.topic_id = t2.id
					WHERE qt2.question_id = q.id 
					  AND t2.name = ANY($2::text[])
				), 0) * 3 +
				COALESCE((
					SELECT COUNT(*) FROM question_subtopics qst2
					JOIN subtopics st2 ON qst2.subtopic_id = st2.id
					WHERE qst2.question_id = q.id 
					  AND st2.name = ANY($3::text[])
				), 0) * 2 +
				COALESCE((
					SELECT COUNT(*) FROM question_tags qtag2
					JOIN tags tag2 ON qtag2.tag_id = tag2.id
					WHERE qtag2.question_id = q.id 
					  AND tag2.name = ANY($4::text[])
				), 0) * 1 +
				CASE WHEN EXISTS (
					SELECT 1 FROM question_topics qt3
					JOIN topics t3 ON qt3.topic_id = t3.id
					WHERE qt3.question_id = q.id 
					  AND t3.name = ANY($2::text[])
				) THEN 2 ELSE 0 END
			) as similarity_score
		FROM questions q
		WHERE q.module_id = $5
		  AND q.id != $1
		  AND q.answer IS NOT NULL
		  AND q.answer != ''
		ORDER BY similarity_score DESC, random()
		LIMIT $6
	`

	rows, err := db.Pool.Query(ctx, query, questionID, questionTopics, questionSubtopics, questionTags, moduleID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var distractors []Distractor
	for rows.Next() {
		var d Distractor
		var score int
		if err := rows.Scan(&d.ID, &d.Answer, &score); err != nil {
			return nil, err
		}
		d.Type = "question"
		distractors = append(distractors, d)
	}
	return distractors, rows.Err()
}

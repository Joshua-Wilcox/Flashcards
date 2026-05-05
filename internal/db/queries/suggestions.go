package queries

import (
	"context"

	"flashcards-go/internal/db"
)

type Suggestion struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

func GetTopicSuggestions(ctx context.Context, moduleID int, query string) ([]Suggestion, error) {
	var q string
	var args []interface{}
	if query == "" {
		q = `
			SELECT t.name, COUNT(DISTINCT qt.question_id) as count
			FROM topics t
			JOIN question_topics qt ON t.id = qt.topic_id
			JOIN questions qn ON qt.question_id = qn.id
			WHERE qn.module_id = $1
			GROUP BY t.name
			ORDER BY count DESC
			LIMIT 10
		`
		args = []interface{}{moduleID}
	} else {
		q = `
			SELECT t.name, COUNT(DISTINCT qt.question_id) as count
			FROM topics t
			JOIN question_topics qt ON t.id = qt.topic_id
			JOIN questions qn ON qt.question_id = qn.id
			WHERE qn.module_id = $1 AND t.name ILIKE '%' || $2 || '%'
			GROUP BY t.name
			ORDER BY count DESC
			LIMIT 10
		`
		args = []interface{}{moduleID, query}
	}

	rows, err := db.Pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var suggestions []Suggestion
	for rows.Next() {
		var s Suggestion
		if err := rows.Scan(&s.Name, &s.Count); err != nil {
			return nil, err
		}
		suggestions = append(suggestions, s)
	}
	return suggestions, rows.Err()
}

func GetSubtopicSuggestions(ctx context.Context, moduleID int, topicName, query string) ([]Suggestion, error) {
	var q string
	var args []interface{}
	if topicName == "" {
		if query == "" {
			q = `
				SELECT st.name, COUNT(DISTINCT qst.question_id) as count
				FROM subtopics st
				JOIN question_subtopics qst ON st.id = qst.subtopic_id
				JOIN questions qn ON qst.question_id = qn.id
				WHERE qn.module_id = $1
				GROUP BY st.name
				ORDER BY count DESC
				LIMIT 10
			`
			args = []interface{}{moduleID}
		} else {
			q = `
				SELECT st.name, COUNT(DISTINCT qst.question_id) as count
				FROM subtopics st
				JOIN question_subtopics qst ON st.id = qst.subtopic_id
				JOIN questions qn ON qst.question_id = qn.id
				WHERE qn.module_id = $1 AND st.name ILIKE '%' || $2 || '%'
				GROUP BY st.name
				ORDER BY count DESC
				LIMIT 10
			`
			args = []interface{}{moduleID, query}
		}
	} else {
		if query == "" {
			q = `
				SELECT st.name, COUNT(DISTINCT qst.question_id) as count
				FROM subtopics st
				JOIN question_subtopics qst ON st.id = qst.subtopic_id
				JOIN questions qn ON qst.question_id = qn.id
				JOIN question_topics qt ON qn.id = qt.question_id
				JOIN topics t ON qt.topic_id = t.id
				WHERE qn.module_id = $1 AND t.name = $2
				GROUP BY st.name
				ORDER BY count DESC
				LIMIT 10
			`
			args = []interface{}{moduleID, topicName}
		} else {
			q = `
				SELECT st.name, COUNT(DISTINCT qst.question_id) as count
				FROM subtopics st
				JOIN question_subtopics qst ON st.id = qst.subtopic_id
				JOIN questions qn ON qst.question_id = qn.id
				JOIN question_topics qt ON qn.id = qt.question_id
				JOIN topics t ON qt.topic_id = t.id
				WHERE qn.module_id = $1 AND t.name = $2 AND st.name ILIKE '%' || $3 || '%'
				GROUP BY st.name
				ORDER BY count DESC
				LIMIT 10
			`
			args = []interface{}{moduleID, topicName, query}
		}
	}

	rows, err := db.Pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var suggestions []Suggestion
	for rows.Next() {
		var s Suggestion
		if err := rows.Scan(&s.Name, &s.Count); err != nil {
			return nil, err
		}
		suggestions = append(suggestions, s)
	}
	return suggestions, rows.Err()
}

func GetTagSuggestions(ctx context.Context, moduleID int, query string) ([]Suggestion, error) {
	var q string
	var args []interface{}
	if query == "" {
		q = `
			SELECT tag.name, COUNT(DISTINCT qtag.question_id) as count
			FROM tags tag
			JOIN question_tags qtag ON tag.id = qtag.tag_id
			JOIN questions qn ON qtag.question_id = qn.id
			WHERE qn.module_id = $1 AND tag.name NOT LIKE '%,%'
			GROUP BY tag.name
			ORDER BY count DESC
			LIMIT 20
		`
		args = []interface{}{moduleID}
	} else {
		q = `
			SELECT tag.name, COUNT(DISTINCT qtag.question_id) as count
			FROM tags tag
			JOIN question_tags qtag ON tag.id = qtag.tag_id
			JOIN questions qn ON qtag.question_id = qn.id
			WHERE qn.module_id = $1 AND tag.name ILIKE '%' || $2 || '%' AND tag.name NOT LIKE '%,%'
			GROUP BY tag.name
			ORDER BY count DESC
			LIMIT 20
		`
		args = []interface{}{moduleID, query}
	}

	rows, err := db.Pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var suggestions []Suggestion
	for rows.Next() {
		var s Suggestion
		if err := rows.Scan(&s.Name, &s.Count); err != nil {
			return nil, err
		}
		suggestions = append(suggestions, s)
	}
	return suggestions, rows.Err()
}

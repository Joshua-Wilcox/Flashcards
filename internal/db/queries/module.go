package queries

import (
	"context"

	"flashcards-go/internal/db"

	"github.com/jackc/pgx/v5"
)

type Module struct {
	ID   int     `json:"id"`
	Name string  `json:"name"`
	Year *int    `json:"year,omitempty"`
}

func GetAllModules(ctx context.Context) ([]Module, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT id, name, year
		FROM modules
		ORDER BY year NULLS LAST, name
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var modules []Module
	for rows.Next() {
		var m Module
		if err := rows.Scan(&m.ID, &m.Name, &m.Year); err != nil {
			return nil, err
		}
		modules = append(modules, m)
	}
	return modules, rows.Err()
}

func GetModuleIDByName(ctx context.Context, name string) (int, error) {
	var id int
	err := db.Pool.QueryRow(ctx, `SELECT id FROM modules WHERE name = $1`, name).Scan(&id)
	if err == pgx.ErrNoRows {
		return 0, nil
	}
	return id, err
}

type FilterItem struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

func GetModuleFilterData(ctx context.Context, moduleID int, selectedTopics []string) (topics, subtopics, tags []FilterItem, err error) {
	topicsQuery := `
		SELECT t.name, COUNT(DISTINCT q.id) as count
		FROM topics t
		JOIN question_topics qt ON t.id = qt.topic_id
		JOIN questions q ON qt.question_id = q.id
		WHERE q.module_id = $1
		GROUP BY t.name
		ORDER BY t.name
	`
	rows, err := db.Pool.Query(ctx, topicsQuery, moduleID)
	if err != nil {
		return nil, nil, nil, err
	}
	for rows.Next() {
		var item FilterItem
		if err := rows.Scan(&item.Name, &item.Count); err != nil {
			rows.Close()
			return nil, nil, nil, err
		}
		topics = append(topics, item)
	}
	rows.Close()

	subtopicsQuery := `
		SELECT st.name, COUNT(DISTINCT q.id) as count
		FROM subtopics st
		JOIN question_subtopics qst ON st.id = qst.subtopic_id
		JOIN questions q ON qst.question_id = q.id
		WHERE q.module_id = $1
		  AND ($2::text[] IS NULL OR array_length($2::text[], 1) IS NULL OR EXISTS (
			SELECT 1 FROM question_topics qt2
			JOIN topics t2 ON qt2.topic_id = t2.id
			WHERE qt2.question_id = q.id AND t2.name = ANY($2)
		  ))
		GROUP BY st.name
		ORDER BY st.name
	`
	rows, err = db.Pool.Query(ctx, subtopicsQuery, moduleID, selectedTopics)
	if err != nil {
		return nil, nil, nil, err
	}
	for rows.Next() {
		var item FilterItem
		if err := rows.Scan(&item.Name, &item.Count); err != nil {
			rows.Close()
			return nil, nil, nil, err
		}
		subtopics = append(subtopics, item)
	}
	rows.Close()

	tagsQuery := `
		SELECT tag.name, COUNT(DISTINCT q.id) as count
		FROM tags tag
		JOIN question_tags qtag ON tag.id = qtag.tag_id
		JOIN questions q ON qtag.question_id = q.id
		WHERE q.module_id = $1
		  AND ($2::text[] IS NULL OR array_length($2::text[], 1) IS NULL OR EXISTS (
			SELECT 1 FROM question_topics qt2
			JOIN topics t2 ON qt2.topic_id = t2.id
			WHERE qt2.question_id = q.id AND t2.name = ANY($2)
		  ))
		GROUP BY tag.name
		ORDER BY tag.name
	`
	rows, err = db.Pool.Query(ctx, tagsQuery, moduleID, selectedTopics)
	if err != nil {
		return nil, nil, nil, err
	}
	for rows.Next() {
		var item FilterItem
		if err := rows.Scan(&item.Name, &item.Count); err != nil {
			rows.Close()
			return nil, nil, nil, err
		}
		tags = append(tags, item)
	}
	rows.Close()

	return topics, subtopics, tags, rows.Err()
}

func GroupModulesByYear(modules []Module) map[string][]Module {
	groups := make(map[string][]Module)
	for _, m := range modules {
		var key string
		if m.Year != nil {
			key = "Year " + string(rune('0'+*m.Year))
		} else {
			key = "Other"
		}
		groups[key] = append(groups[key], m)
	}
	return groups
}

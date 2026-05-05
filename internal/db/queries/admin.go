package queries

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strconv"
	"time"

	"flashcards-go/internal/db"

	"github.com/jackc/pgx/v5"
)

type SubmittedFlashcard struct {
	ID                        int        `json:"id"`
	UserID                    string     `json:"user_id"`
	Username                  *string    `json:"username"`
	SubmittedQuestion         string     `json:"submitted_question"`
	SubmittedAnswer           string     `json:"submitted_answer"`
	Module                    string     `json:"module"`
	SubmittedTopic            *string    `json:"submitted_topic"`
	SubmittedSubtopic         *string    `json:"submitted_subtopic"`
	SubmittedTagsCommaSeparated *string  `json:"submitted_tags_comma_separated"`
	CreatedAt                 time.Time  `json:"created_at"`
}

type SubmittedDistractor struct {
	ID             int       `json:"id"`
	UserID         string    `json:"user_id"`
	Username       *string   `json:"username"`
	QuestionID     string    `json:"question_id"`
	DistractorText string    `json:"distractor_text"`
	CreatedAt      time.Time `json:"created_at"`
	QuestionText   *string   `json:"question_text,omitempty"`
	QuestionSource string    `json:"question_source,omitempty"`
}

type ReportedQuestion struct {
	ID          int       `json:"id"`
	UserID      string    `json:"user_id"`
	Username    string    `json:"username"`
	Question    string    `json:"question"`
	QuestionID  *string   `json:"question_id"`
	Message     *string   `json:"message"`
	Distractors *string   `json:"distractors"`
	CreatedAt   time.Time `json:"created_at"`
}

type PDFAccessRequest struct {
	ID        int       `json:"id"`
	DiscordID string    `json:"discord_id"`
	Username  string    `json:"username"`
	Message   *string   `json:"message"`
	CreatedAt time.Time `json:"created_at"`
}

func GetSubmittedFlashcards(ctx context.Context) ([]SubmittedFlashcard, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT id, user_id, username, submitted_question, submitted_answer, 
		       module, submitted_topic, submitted_subtopic, 
		       submitted_tags_comma_separated, created_at
		FROM submitted_flashcards
		ORDER BY created_at
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var submissions []SubmittedFlashcard
	for rows.Next() {
		var s SubmittedFlashcard
		if err := rows.Scan(&s.ID, &s.UserID, &s.Username, &s.SubmittedQuestion,
			&s.SubmittedAnswer, &s.Module, &s.SubmittedTopic, &s.SubmittedSubtopic,
			&s.SubmittedTagsCommaSeparated, &s.CreatedAt); err != nil {
			return nil, err
		}
		submissions = append(submissions, s)
	}
	return submissions, rows.Err()
}

func GetSubmittedFlashcardByID(ctx context.Context, id int) (*SubmittedFlashcard, error) {
	var s SubmittedFlashcard
	err := db.Pool.QueryRow(ctx, `
		SELECT id, user_id, username, submitted_question, submitted_answer, 
		       module, submitted_topic, submitted_subtopic, 
		       submitted_tags_comma_separated, created_at
		FROM submitted_flashcards
		WHERE id = $1
	`, id).Scan(&s.ID, &s.UserID, &s.Username, &s.SubmittedQuestion,
		&s.SubmittedAnswer, &s.Module, &s.SubmittedTopic, &s.SubmittedSubtopic,
		&s.SubmittedTagsCommaSeparated, &s.CreatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &s, nil
}

func GetSubmittedDistractors(ctx context.Context) ([]SubmittedDistractor, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT sd.id, sd.user_id, sd.username, sd.question_id, sd.distractor_text, sd.created_at,
		       COALESCE(q.question, sf.submitted_question) as question_text,
		       CASE WHEN q.question IS NOT NULL THEN 'live' ELSE 'pending' END as question_source
		FROM submitted_distractors sd
		LEFT JOIN questions q ON sd.question_id = q.id
		LEFT JOIN submitted_flashcards sf ON sd.question_id = ('flashcard_' || sf.id::text)
		ORDER BY COALESCE(q.question, sf.submitted_question) NULLS LAST, sd.created_at
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var submissions []SubmittedDistractor
	for rows.Next() {
		var s SubmittedDistractor
		if err := rows.Scan(&s.ID, &s.UserID, &s.Username, &s.QuestionID,
			&s.DistractorText, &s.CreatedAt, &s.QuestionText, &s.QuestionSource); err != nil {
			return nil, err
		}
		submissions = append(submissions, s)
	}
	return submissions, rows.Err()
}

func GetSubmittedDistractorByID(ctx context.Context, id int) (*SubmittedDistractor, error) {
	var s SubmittedDistractor
	err := db.Pool.QueryRow(ctx, `
		SELECT sd.id, sd.user_id, sd.username, sd.question_id, sd.distractor_text, sd.created_at
		FROM submitted_distractors sd
		WHERE sd.id = $1
	`, id).Scan(&s.ID, &s.UserID, &s.Username, &s.QuestionID, &s.DistractorText, &s.CreatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	var questionText string
	err = db.Pool.QueryRow(ctx, `SELECT question FROM questions WHERE id = $1`, s.QuestionID).Scan(&questionText)
	if err == nil {
		s.QuestionText = &questionText
	}

	return &s, nil
}

func GetReportedQuestions(ctx context.Context) ([]ReportedQuestion, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT id, user_id, username, question, question_id, message, distractors, created_at
		FROM reported_questions
		ORDER BY created_at
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var reports []ReportedQuestion
	for rows.Next() {
		var r ReportedQuestion
		if err := rows.Scan(&r.ID, &r.UserID, &r.Username, &r.Question,
			&r.QuestionID, &r.Message, &r.Distractors, &r.CreatedAt); err != nil {
			return nil, err
		}
		reports = append(reports, r)
	}
	return reports, rows.Err()
}

func GetPDFAccessRequests(ctx context.Context) ([]PDFAccessRequest, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT id, discord_id, username, message, created_at
		FROM requests_to_access
		ORDER BY created_at
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var requests []PDFAccessRequest
	for rows.Next() {
		var r PDFAccessRequest
		if err := rows.Scan(&r.ID, &r.DiscordID, &r.Username, &r.Message, &r.CreatedAt); err != nil {
			return nil, err
		}
		requests = append(requests, r)
	}
	return requests, rows.Err()
}

func GenerateQuestionID(question string) string {
	hash := sha256.Sum256([]byte(question))
	return hex.EncodeToString(hash[:])
}

type ApproveFlashcardResult struct {
	Success                bool   `json:"success"`
	QuestionID             string `json:"question_id,omitempty"`
	PendingDistractorsCount int   `json:"pending_distractors_count"`
	Error                  string `json:"error,omitempty"`
}

func ApproveFlashcard(ctx context.Context, submissionID int, question, answer string, moduleID int, topic, subtopic *string, tags []string) (*ApproveFlashcardResult, error) {
	tx, err := db.Pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var submission SubmittedFlashcard
	err = tx.QueryRow(ctx, `
		SELECT id, user_id, username FROM submitted_flashcards WHERE id = $1
	`, submissionID).Scan(&submission.ID, &submission.UserID, &submission.Username)
	if err == pgx.ErrNoRows {
		return &ApproveFlashcardResult{Success: false, Error: "Submission not found"}, nil
	}
	if err != nil {
		return nil, err
	}

	questionID := GenerateQuestionID(question)

	_, err = tx.Exec(ctx, `
		INSERT INTO questions (id, question, answer, module_id)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (id) DO UPDATE SET
			question = EXCLUDED.question,
			answer = EXCLUDED.answer,
			module_id = EXCLUDED.module_id,
			updated_at = NOW()
	`, questionID, question, answer, moduleID)
	if err != nil {
		return nil, err
	}

	if topic != nil && *topic != "" {
		var topicID int
		err = tx.QueryRow(ctx, `
			INSERT INTO topics (name) VALUES ($1)
			ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
			RETURNING id
		`, *topic).Scan(&topicID)
		if err != nil {
			return nil, err
		}
		_, err = tx.Exec(ctx, `
			INSERT INTO question_topics (question_id, topic_id) VALUES ($1, $2)
			ON CONFLICT DO NOTHING
		`, questionID, topicID)
		if err != nil {
			return nil, err
		}
	}

	if subtopic != nil && *subtopic != "" {
		var subtopicID int
		err = tx.QueryRow(ctx, `
			INSERT INTO subtopics (name) VALUES ($1)
			ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
			RETURNING id
		`, *subtopic).Scan(&subtopicID)
		if err != nil {
			return nil, err
		}
		_, err = tx.Exec(ctx, `
			INSERT INTO question_subtopics (question_id, subtopic_id) VALUES ($1, $2)
			ON CONFLICT DO NOTHING
		`, questionID, subtopicID)
		if err != nil {
			return nil, err
		}
	}

	for _, tagName := range tags {
		if tagName == "" {
			continue
		}
		var tagID int
		err = tx.QueryRow(ctx, `
			INSERT INTO tags (name) VALUES ($1)
			ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
			RETURNING id
		`, tagName).Scan(&tagID)
		if err != nil {
			return nil, err
		}
		_, err = tx.Exec(ctx, `
			INSERT INTO question_tags (question_id, tag_id) VALUES ($1, $2)
			ON CONFLICT DO NOTHING
		`, questionID, tagID)
		if err != nil {
			return nil, err
		}
	}

	_, err = tx.Exec(ctx, `
		INSERT INTO user_stats (user_id, username, approved_cards)
		VALUES ($1, $2, 1)
		ON CONFLICT (user_id) DO UPDATE SET
			approved_cards = user_stats.approved_cards + 1
	`, submission.UserID, submission.Username)
	if err != nil {
		return nil, err
	}

	oldKey := "flashcard_" + strconv.Itoa(submissionID)
	var pendingCount int
	err = tx.QueryRow(ctx, `
		UPDATE submitted_distractors SET question_id = $1
		WHERE question_id = $2
		RETURNING (SELECT COUNT(*) FROM submitted_distractors WHERE question_id = $1)
	`, questionID, oldKey).Scan(&pendingCount)
	if err != nil && err != pgx.ErrNoRows {
		err = tx.QueryRow(ctx, `SELECT COUNT(*) FROM submitted_distractors WHERE question_id = $1`, questionID).Scan(&pendingCount)
		if err != nil {
			return nil, err
		}
	}

	_, err = tx.Exec(ctx, `DELETE FROM submitted_flashcards WHERE id = $1`, submissionID)
	if err != nil {
		return nil, err
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}

	return &ApproveFlashcardResult{
		Success:                true,
		QuestionID:             questionID,
		PendingDistractorsCount: pendingCount,
	}, nil
}

func RejectFlashcard(ctx context.Context, submissionID int) (int, error) {
	tx, err := db.Pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx)

	oldKey := "flashcard_" + strconv.Itoa(submissionID)
	var rejectedCount int
	err = tx.QueryRow(ctx, `
		WITH deleted AS (
			DELETE FROM submitted_distractors WHERE question_id = $1 RETURNING 1
		)
		SELECT COUNT(*) FROM deleted
	`, oldKey).Scan(&rejectedCount)
	if err != nil {
		return 0, err
	}

	_, err = tx.Exec(ctx, `DELETE FROM submitted_flashcards WHERE id = $1`, submissionID)
	if err != nil {
		return 0, err
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}

	return rejectedCount, nil
}

func ApproveDistractor(ctx context.Context, submissionID int) (int, error) {
	tx, err := db.Pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx)

	var submission SubmittedDistractor
	err = tx.QueryRow(ctx, `
		SELECT id, user_id, username, question_id, distractor_text
		FROM submitted_distractors WHERE id = $1
	`, submissionID).Scan(&submission.ID, &submission.UserID, &submission.Username,
		&submission.QuestionID, &submission.DistractorText)
	if err == pgx.ErrNoRows {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}

	var distractorID int
	err = tx.QueryRow(ctx, `
		INSERT INTO manual_distractors (question_id, distractor_text, created_by)
		VALUES ($1, $2, $3)
		RETURNING id
	`, submission.QuestionID, submission.DistractorText, submission.UserID).Scan(&distractorID)
	if err != nil {
		return 0, err
	}

	_, err = tx.Exec(ctx, `
		INSERT INTO user_stats (user_id, username, approved_cards)
		VALUES ($1, $2, 1)
		ON CONFLICT (user_id) DO UPDATE SET
			approved_cards = user_stats.approved_cards + 1
	`, submission.UserID, submission.Username)
	if err != nil {
		return 0, err
	}

	_, err = tx.Exec(ctx, `DELETE FROM submitted_distractors WHERE id = $1`, submissionID)
	if err != nil {
		return 0, err
	}

	if err := tx.Commit(ctx); err != nil {
		return 0, err
	}

	return distractorID, nil
}

func RejectDistractor(ctx context.Context, submissionID int) error {
	_, err := db.Pool.Exec(ctx, `DELETE FROM submitted_distractors WHERE id = $1`, submissionID)
	return err
}

func DeleteReportedQuestion(ctx context.Context, reportID int) error {
	_, err := db.Pool.Exec(ctx, `DELETE FROM reported_questions WHERE id = $1`, reportID)
	return err
}

func DeletePDFAccessRequest(ctx context.Context, requestID int) error {
	_, err := db.Pool.Exec(ctx, `DELETE FROM requests_to_access WHERE id = $1`, requestID)
	return err
}

// LiveQuestion holds the current DB state of a question for report review.
type LiveQuestion struct {
	ID       string `json:"id"`
	Question string `json:"question"`
	Answer   string `json:"answer"`
}

// LiveManualDistractor holds a manual distractor for report review.
type LiveManualDistractor struct {
	ID             int    `json:"id"`
	DistractorText string `json:"distractor_text"`
}

func GetLiveQuestion(ctx context.Context, questionID string) (*LiveQuestion, error) {
	var q LiveQuestion
	err := db.Pool.QueryRow(ctx, `SELECT id, question, answer FROM questions WHERE id = $1`, questionID).
		Scan(&q.ID, &q.Question, &q.Answer)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &q, err
}

func GetManualDistractorsForQuestion(ctx context.Context, questionID string) ([]LiveManualDistractor, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT id, distractor_text FROM manual_distractors WHERE question_id = $1 ORDER BY id
	`, questionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var ds []LiveManualDistractor
	for rows.Next() {
		var d LiveManualDistractor
		if err := rows.Scan(&d.ID, &d.DistractorText); err != nil {
			return nil, err
		}
		ds = append(ds, d)
	}
	return ds, rows.Err()
}

func UpdateQuestionText(ctx context.Context, questionID, newText string) error {
	_, err := db.Pool.Exec(ctx, `UPDATE questions SET question = $1, updated_at = NOW() WHERE id = $2`, newText, questionID)
	return err
}

func DeleteQuestion(ctx context.Context, questionID string) error {
	_, err := db.Pool.Exec(ctx, `DELETE FROM questions WHERE id = $1`, questionID)
	return err
}

func DeleteManualDistractorByID(ctx context.Context, distractorID int) error {
	_, err := db.Pool.Exec(ctx, `DELETE FROM manual_distractors WHERE id = $1`, distractorID)
	return err
}

func UpdateQuestionAnswer(ctx context.Context, questionID, newAnswer string) error {
	_, err := db.Pool.Exec(ctx, `
		UPDATE questions SET answer = $1, updated_at = NOW() WHERE id = $2
	`, newAnswer, questionID)
	return err
}

func UpdateManualDistractor(ctx context.Context, distractorID int, newText string) error {
	_, err := db.Pool.Exec(ctx, `
		UPDATE manual_distractors SET distractor_text = $1 WHERE id = $2
	`, newText, distractorID)
	return err
}

func InsertSubmittedFlashcard(ctx context.Context, userID, username, question, answer, module string, topic, subtopic, tags *string) (int, error) {
	var id int
	err := db.Pool.QueryRow(ctx, `
		INSERT INTO submitted_flashcards (user_id, username, submitted_question, submitted_answer, 
		                                  module, submitted_topic, submitted_subtopic, submitted_tags_comma_separated)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		RETURNING id
	`, userID, username, question, answer, module, topic, subtopic, tags).Scan(&id)
	return id, err
}

func InsertSubmittedDistractor(ctx context.Context, userID, username, questionID, distractorText string) error {
	_, err := db.Pool.Exec(ctx, `
		INSERT INTO submitted_distractors (user_id, username, question_id, distractor_text)
		VALUES ($1, $2, $3, $4)
	`, userID, username, questionID, distractorText)
	return err
}

func InsertReportedQuestion(ctx context.Context, userID, username, question string, questionID *string, message, distractors *string) error {
	_, err := db.Pool.Exec(ctx, `
		INSERT INTO reported_questions (user_id, username, question, question_id, message, distractors)
		VALUES ($1, $2, $3, $4, $5, $6)
	`, userID, username, question, questionID, message, distractors)
	return err
}

func InsertPDFAccessRequest(ctx context.Context, discordID, username string, message *string) error {
	_, err := db.Pool.Exec(ctx, `
		INSERT INTO requests_to_access (discord_id, username, message)
		VALUES ($1, $2, $3)
	`, discordID, username, message)
	return err
}

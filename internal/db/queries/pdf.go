package queries

import (
	"context"
	"strconv"

	"flashcards-go/internal/db"

	"github.com/jackc/pgx/v5"
)

// SubmittedPDF represents a PDF awaiting admin approval
type SubmittedPDF struct {
	ID               int      `json:"id"`
	StoragePath      string   `json:"storage_path"`
	OriginalFilename string   `json:"original_filename"`
	FileSize         *int64   `json:"file_size,omitempty"`
	MimeType         string   `json:"mime_type"`
	ModuleID         *int     `json:"module_id,omitempty"`
	ModuleName       string   `json:"module_name,omitempty"`
	UploadedBy       string   `json:"uploaded_by"`
	Username         string   `json:"username,omitempty"`
	SubmittedAt      string   `json:"submitted_at,omitempty"`
	TopicIDs         []int    `json:"topic_ids"`
	SubtopicIDs      []int    `json:"subtopic_ids"`
	TagIDs           []int    `json:"tag_ids"`
	TopicNames       []string `json:"topic_names,omitempty"`
	SubtopicNames    []string `json:"subtopic_names,omitempty"`
	TagNames         []string `json:"tag_names,omitempty"`
	URL              string   `json:"url,omitempty"`
}

// InsertSubmittedPDF inserts a PDF into the pending approval queue
func InsertSubmittedPDF(ctx context.Context, pdf PDFInsert, topicIDs, subtopicIDs, tagIDs []int) (int, error) {
	var id int
	err := db.Pool.QueryRow(ctx, `
		INSERT INTO submitted_pdfs (storage_path, original_filename, file_size, mime_type, module_id, uploaded_by, topic_ids, subtopic_ids, tag_ids)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		RETURNING id
	`, pdf.StoragePath, pdf.OriginalFilename, pdf.FileSize, pdf.MimeType, pdf.ModuleID, pdf.UploadedBy,
		topicIDs, subtopicIDs, tagIDs).Scan(&id)
	return id, err
}

// ListSubmittedPDFs returns all PDFs pending approval, with resolved names
func ListSubmittedPDFs(ctx context.Context) ([]SubmittedPDF, error) {
	rows, err := db.Pool.Query(ctx, `
		SELECT sp.id, sp.storage_path, sp.original_filename, sp.file_size,
		       sp.mime_type, sp.module_id, COALESCE(m.name, ''), sp.uploaded_by,
		       sp.submitted_at::text, sp.topic_ids, sp.subtopic_ids, sp.tag_ids
		FROM submitted_pdfs sp
		LEFT JOIN modules m ON sp.module_id = m.id
		ORDER BY sp.submitted_at DESC
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []SubmittedPDF
	for rows.Next() {
		var p SubmittedPDF
		var topicIDs, subtopicIDs, tagIDs []int
		if err := rows.Scan(
			&p.ID, &p.StoragePath, &p.OriginalFilename, &p.FileSize,
			&p.MimeType, &p.ModuleID, &p.ModuleName, &p.UploadedBy,
			&p.SubmittedAt, &topicIDs, &subtopicIDs, &tagIDs,
		); err != nil {
			return nil, err
		}
		if topicIDs == nil {
			topicIDs = []int{}
		}
		if subtopicIDs == nil {
			subtopicIDs = []int{}
		}
		if tagIDs == nil {
			tagIDs = []int{}
		}
		p.TopicIDs = topicIDs
		p.SubtopicIDs = subtopicIDs
		p.TagIDs = tagIDs

		// Resolve names
		p.TopicNames = ResolveTopicNames(ctx, topicIDs)
		p.SubtopicNames = ResolveSubtopicNames(ctx, subtopicIDs)
		p.TagNames = ResolveTagNames(ctx, tagIDs)
		p.URL = "/api/pdf/submitted/" + strconv.Itoa(p.ID)
		results = append(results, p)
	}
	return results, rows.Err()
}

// ApproveSubmittedPDF moves a submitted PDF into the live pdfs table
func ApproveSubmittedPDF(ctx context.Context, submittedID int) (int, error) {
	tx, err := db.Pool.Begin(ctx)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback(ctx)

	var p SubmittedPDF
	var topicIDs, subtopicIDs, tagIDs []int
	err = tx.QueryRow(ctx, `
		SELECT id, storage_path, original_filename, file_size, mime_type, module_id, uploaded_by,
		       topic_ids, subtopic_ids, tag_ids
		FROM submitted_pdfs WHERE id = $1
	`, submittedID).Scan(
		&p.ID, &p.StoragePath, &p.OriginalFilename, &p.FileSize, &p.MimeType, &p.ModuleID, &p.UploadedBy,
		&topicIDs, &subtopicIDs, &tagIDs,
	)
	if err != nil {
		return 0, err
	}

	// Insert into live pdfs
	var newID int
	err = tx.QueryRow(ctx, `
		INSERT INTO pdfs (storage_path, original_filename, file_size, mime_type, module_id, uploaded_by, is_active)
		VALUES ($1, $2, $3, $4, $5, $6, true)
		RETURNING id
	`, p.StoragePath, p.OriginalFilename, p.FileSize, p.MimeType, p.ModuleID, p.UploadedBy).Scan(&newID)
	if err != nil {
		return 0, err
	}

	// Link topics
	for _, topicID := range topicIDs {
		tx.Exec(ctx, `INSERT INTO pdf_topics (pdf_id, topic_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`, newID, topicID)
	}
	// Link subtopics
	for _, subtopicID := range subtopicIDs {
		tx.Exec(ctx, `INSERT INTO pdf_subtopics (pdf_id, subtopic_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`, newID, subtopicID)
	}
	// Link tags
	for _, tagID := range tagIDs {
		tx.Exec(ctx, `INSERT INTO pdf_tags (pdf_id, tag_id, count) VALUES ($1, $2, 1) ON CONFLICT DO NOTHING`, newID, tagID)
	}

	// Remove from submitted
	_, err = tx.Exec(ctx, `DELETE FROM submitted_pdfs WHERE id = $1`, submittedID)
	if err != nil {
		return 0, err
	}

	return newID, tx.Commit(ctx)
}

// RejectSubmittedPDF deletes a submitted PDF and returns its storage_path for cleanup
func RejectSubmittedPDF(ctx context.Context, submittedID int) (string, error) {
	var storagePath string
	err := db.Pool.QueryRow(ctx, `DELETE FROM submitted_pdfs WHERE id = $1 RETURNING storage_path`, submittedID).Scan(&storagePath)
	return storagePath, err
}

// GetSubmittedPDFByID returns a single submitted PDF for serving its file
func GetSubmittedPDFByID(ctx context.Context, id int) (*SubmittedPDF, error) {
	var p SubmittedPDF
	err := db.Pool.QueryRow(ctx, `
		SELECT sp.id, sp.storage_path, sp.original_filename, sp.file_size, sp.mime_type
		FROM submitted_pdfs sp WHERE sp.id = $1
	`, id).Scan(&p.ID, &p.StoragePath, &p.OriginalFilename, &p.FileSize, &p.MimeType)
	if err != nil {
		return nil, err
	}
	return &p, nil
}

// ResolveTopicNames resolves topic IDs to names
func ResolveTopicNames(ctx context.Context, ids []int) []string {
	if len(ids) == 0 {
		return []string{}
	}
	names := make([]string, 0, len(ids))
	for _, id := range ids {
		var name string
		if err := db.Pool.QueryRow(ctx, `SELECT name FROM topics WHERE id = $1`, id).Scan(&name); err == nil {
			names = append(names, name)
		}
	}
	return names
}

// ResolveSubtopicNames resolves subtopic IDs to names
func ResolveSubtopicNames(ctx context.Context, ids []int) []string {
	if len(ids) == 0 {
		return []string{}
	}
	names := make([]string, 0, len(ids))
	for _, id := range ids {
		var name string
		if err := db.Pool.QueryRow(ctx, `SELECT name FROM subtopics WHERE id = $1`, id).Scan(&name); err == nil {
			names = append(names, name)
		}
	}
	return names
}

// ResolveTagNames resolves tag IDs to names
func ResolveTagNames(ctx context.Context, ids []int) []string {
	if len(ids) == 0 {
		return []string{}
	}
	names := make([]string, 0, len(ids))
	for _, id := range ids {
		var name string
		if err := db.Pool.QueryRow(ctx, `SELECT name FROM tags WHERE id = $1`, id).Scan(&name); err == nil {
			names = append(names, name)
		}
	}
	return names
}

type PDF struct {
	ID               int      `json:"id"`
	StoragePath      string   `json:"storage_path"`
	OriginalFilename string   `json:"original_filename"`
	FileSize         *int64   `json:"file_size,omitempty"`
	MimeType         string   `json:"mime_type"`
	ModuleID         *int     `json:"module_id,omitempty"`
	ModuleName       string   `json:"module_name,omitempty"`
	IsActive         bool     `json:"is_active"`
	MatchPercent     float64  `json:"match_percent,omitempty"`
	MatchReasons     []string `json:"match_reasons,omitempty"`
	URL              string   `json:"url,omitempty"`
	TopicIDs         []int    `json:"topic_ids,omitempty"`
	SubtopicIDs      []int    `json:"subtopic_ids,omitempty"`
	TagIDs           []int    `json:"tag_ids,omitempty"`
	TopicNames       []string `json:"topic_names,omitempty"`
	SubtopicNames    []string `json:"subtopic_names,omitempty"`
	TagNames         []string `json:"tag_names,omitempty"`
}

type PDFInsert struct {
	StoragePath      string
	OriginalFilename string
	FileSize         int64
	MimeType         string
	ModuleID         int
	UploadedBy       string
}

// InsertPDF inserts a new PDF record and returns the ID
func InsertPDF(ctx context.Context, pdf PDFInsert) (int, error) {
	var id int
	err := db.Pool.QueryRow(ctx, `
		INSERT INTO pdfs (storage_path, original_filename, file_size, mime_type, module_id, uploaded_by, is_active)
		VALUES ($1, $2, $3, $4, $5, $6, true)
		RETURNING id
	`, pdf.StoragePath, pdf.OriginalFilename, pdf.FileSize, pdf.MimeType, pdf.ModuleID, pdf.UploadedBy).Scan(&id)
	return id, err
}

// UpdatePDFMetadata updates the metadata for a PDF
func UpdatePDFMetadata(ctx context.Context, pdfID int, moduleID int) error {
	_, err := db.Pool.Exec(ctx, `
		UPDATE pdfs SET module_id = $2 WHERE id = $1
	`, pdfID, moduleID)
	return err
}

// SetPDFTopics replaces all topics for a PDF
func SetPDFTopics(ctx context.Context, pdfID int, topicIDs []int) error {
	tx, err := db.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	// Delete existing topics
	_, err = tx.Exec(ctx, `DELETE FROM pdf_topics WHERE pdf_id = $1`, pdfID)
	if err != nil {
		return err
	}

	// Insert new topics
	for _, topicID := range topicIDs {
		_, err = tx.Exec(ctx, `INSERT INTO pdf_topics (pdf_id, topic_id) VALUES ($1, $2)`, pdfID, topicID)
		if err != nil {
			return err
		}
	}

	return tx.Commit(ctx)
}

// SetPDFSubtopics replaces all subtopics for a PDF
func SetPDFSubtopics(ctx context.Context, pdfID int, subtopicIDs []int) error {
	tx, err := db.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	// Delete existing subtopics
	_, err = tx.Exec(ctx, `DELETE FROM pdf_subtopics WHERE pdf_id = $1`, pdfID)
	if err != nil {
		return err
	}

	// Insert new subtopics
	for _, subtopicID := range subtopicIDs {
		_, err = tx.Exec(ctx, `INSERT INTO pdf_subtopics (pdf_id, subtopic_id) VALUES ($1, $2)`, pdfID, subtopicID)
		if err != nil {
			return err
		}
	}

	return tx.Commit(ctx)
}

// SetPDFTags replaces all tags for a PDF
func SetPDFTags(ctx context.Context, pdfID int, tagIDs []int) error {
	tx, err := db.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	// Delete existing tags
	_, err = tx.Exec(ctx, `DELETE FROM pdf_tags WHERE pdf_id = $1`, pdfID)
	if err != nil {
		return err
	}

	// Insert new tags with count=1
	for _, tagID := range tagIDs {
		_, err = tx.Exec(ctx, `INSERT INTO pdf_tags (pdf_id, tag_id, count) VALUES ($1, $2, 1)`, pdfID, tagID)
		if err != nil {
			return err
		}
	}

	return tx.Commit(ctx)
}

// GetOrCreateTopic gets a topic by name or creates it if it doesn't exist
func GetOrCreateTopic(ctx context.Context, name string) (int, error) {
	var id int
	err := db.Pool.QueryRow(ctx, `SELECT id FROM topics WHERE name = $1`, name).Scan(&id)
	if err == nil {
		return id, nil
	}
	if err != pgx.ErrNoRows {
		return 0, err
	}

	// Create new topic
	err = db.Pool.QueryRow(ctx, `INSERT INTO topics (name) VALUES ($1) RETURNING id`, name).Scan(&id)
	return id, err
}

// GetOrCreateSubtopic gets a subtopic by name or creates it if it doesn't exist
func GetOrCreateSubtopic(ctx context.Context, name string) (int, error) {
	var id int
	err := db.Pool.QueryRow(ctx, `SELECT id FROM subtopics WHERE name = $1`, name).Scan(&id)
	if err == nil {
		return id, nil
	}
	if err != pgx.ErrNoRows {
		return 0, err
	}

	// Create new subtopic
	err = db.Pool.QueryRow(ctx, `INSERT INTO subtopics (name) VALUES ($1) RETURNING id`, name).Scan(&id)
	return id, err
}

// GetOrCreateTag gets a tag by name or creates it if it doesn't exist
func GetOrCreateTag(ctx context.Context, name string) (int, error) {
	var id int
	err := db.Pool.QueryRow(ctx, `SELECT id FROM tags WHERE name = $1`, name).Scan(&id)
	if err == nil {
		return id, nil
	}
	if err != pgx.ErrNoRows {
		return 0, err
	}

	// Create new tag
	err = db.Pool.QueryRow(ctx, `INSERT INTO tags (name) VALUES ($1) RETURNING id`, name).Scan(&id)
	return id, err
}

// RestorePDF marks a soft-deleted PDF as active again
func RestorePDF(ctx context.Context, pdfID int) error {
	_, err := db.Pool.Exec(ctx, `UPDATE pdfs SET is_active = true WHERE id = $1`, pdfID)
	return err
}

// GetAllTopics returns all topics for the PDF form
func GetAllTopics(ctx context.Context) ([]Topic, error) {
	rows, err := db.Pool.Query(ctx, `SELECT id, name FROM topics ORDER BY name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var topics []Topic
	for rows.Next() {
		var t Topic
		if err := rows.Scan(&t.ID, &t.Name); err != nil {
			return nil, err
		}
		topics = append(topics, t)
	}
	return topics, rows.Err()
}

type Topic struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

type Subtopic struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

type Tag struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
}

// GetAllSubtopics returns all subtopics for the PDF form
func GetAllSubtopics(ctx context.Context) ([]Subtopic, error) {
	rows, err := db.Pool.Query(ctx, `SELECT id, name FROM subtopics ORDER BY name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var subtopics []Subtopic
	for rows.Next() {
		var s Subtopic
		if err := rows.Scan(&s.ID, &s.Name); err != nil {
			return nil, err
		}
		subtopics = append(subtopics, s)
	}
	return subtopics, rows.Err()
}

// GetAllTags returns all tags for the PDF form
func GetAllTags(ctx context.Context) ([]Tag, error) {
	rows, err := db.Pool.Query(ctx, `SELECT id, name FROM tags ORDER BY name`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tags []Tag
	for rows.Next() {
		var t Tag
		if err := rows.Scan(&t.ID, &t.Name); err != nil {
			return nil, err
		}
		tags = append(tags, t)
	}
	return tags, rows.Err()
}

// GetPDFTopics returns the topic IDs for a PDF
func GetPDFTopics(ctx context.Context, pdfID int) ([]int, error) {
	rows, err := db.Pool.Query(ctx, `SELECT topic_id FROM pdf_topics WHERE pdf_id = $1`, pdfID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var ids []int
	for rows.Next() {
		var id int
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

// GetPDFSubtopics returns the subtopic IDs for a PDF
func GetPDFSubtopics(ctx context.Context, pdfID int) ([]int, error) {
	rows, err := db.Pool.Query(ctx, `SELECT subtopic_id FROM pdf_subtopics WHERE pdf_id = $1`, pdfID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var ids []int
	for rows.Next() {
		var id int
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

// GetPDFTags returns the tag IDs for a PDF
func GetPDFTags(ctx context.Context, pdfID int) ([]int, error) {
	rows, err := db.Pool.Query(ctx, `SELECT tag_id FROM pdf_tags WHERE pdf_id = $1`, pdfID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var ids []int
	for rows.Next() {
		var id int
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

func GetPDFsForQuestion(ctx context.Context, questionID string, maxPDFs int) ([]PDF, error) {
	// Use the RPC function get_pdfs_for_question_v3 for accurate weighted scoring
	// This matches the Flask implementation exactly:
	// - Topic: 30% weight
	// - Subtopic: 50% weight  
	// - Tags: 20% weight
	query := `
		SELECT 
			pdf_id,
			storage_path,
			original_filename,
			module_name,
			match_percent,
			match_reasons
		FROM get_pdfs_for_question_v3($1, $2)
	`

	rows, err := db.Pool.Query(ctx, query, questionID, maxPDFs)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var pdfs []PDF
	for rows.Next() {
		var p PDF
		var matchReasons []string
		if err := rows.Scan(&p.ID, &p.StoragePath, &p.OriginalFilename, &p.ModuleName, &p.MatchPercent, &matchReasons); err != nil {
			return nil, err
		}
		p.MatchReasons = matchReasons
		p.MimeType = "application/pdf"
		p.IsActive = true
		p.URL = "/api/pdf/" + strconv.Itoa(p.ID)
		pdfs = append(pdfs, p)
	}
	return pdfs, rows.Err()
}

func GetPDFByID(ctx context.Context, pdfID int) (*PDF, error) {
	var p PDF
	err := db.Pool.QueryRow(ctx, `
		SELECT p.id, p.storage_path, p.original_filename, p.file_size, 
		       p.mime_type, p.module_id, m.name, p.is_active
		FROM pdfs p
		LEFT JOIN modules m ON p.module_id = m.id
		WHERE p.id = $1
	`, pdfID).Scan(&p.ID, &p.StoragePath, &p.OriginalFilename, &p.FileSize,
		&p.MimeType, &p.ModuleID, &p.ModuleName, &p.IsActive)
	if err != nil {
		return nil, err
	}
	return &p, nil
}

// GetPDFWithMetadata fetches a PDF and all its topic/subtopic/tag names in a single query
func GetPDFWithMetadata(ctx context.Context, pdfID int) (*PDF, error) {
	var p PDF
	var topicNames, subtopicNames, tagNames []string
	err := db.Pool.QueryRow(ctx, `
		SELECT p.id, p.storage_path, p.original_filename, p.file_size,
		       p.mime_type, p.module_id, COALESCE(m.name, ''), p.is_active,
		       COALESCE(ARRAY(SELECT t.name FROM pdf_topics pt JOIN topics t ON pt.topic_id = t.id WHERE pt.pdf_id = p.id ORDER BY t.name), '{}'),
		       COALESCE(ARRAY(SELECT st.name FROM pdf_subtopics ps JOIN subtopics st ON ps.subtopic_id = st.id WHERE ps.pdf_id = p.id ORDER BY st.name), '{}'),
		       COALESCE(ARRAY(SELECT tg.name FROM pdf_tags ptg JOIN tags tg ON ptg.tag_id = tg.id WHERE ptg.pdf_id = p.id ORDER BY tg.name), '{}')
		FROM pdfs p
		LEFT JOIN modules m ON p.module_id = m.id
		WHERE p.id = $1
	`, pdfID).Scan(
		&p.ID, &p.StoragePath, &p.OriginalFilename, &p.FileSize,
		&p.MimeType, &p.ModuleID, &p.ModuleName, &p.IsActive,
		&topicNames, &subtopicNames, &tagNames,
	)
	if err != nil {
		return nil, err
	}
	p.TopicNames = topicNames
	p.SubtopicNames = subtopicNames
	p.TagNames = tagNames
	p.URL = "/api/pdf/" + strconv.Itoa(p.ID)
	return &p, nil
}

// ListPDFsParams holds filter parameters for listing PDFs
type ListPDFsParams struct {
	ModuleID    *int
	IsActive    bool
	TopicName   string
	SubtopicName string
	TagName     string
	Limit       int
	Offset      int
}

func ListPDFs(ctx context.Context, params ListPDFsParams) ([]PDF, int, error) {
	// Build WHERE conditions
	conditions := []string{"p.is_active = $1"}
	args := []interface{}{params.IsActive}
	argN := 2

	if params.ModuleID != nil {
		conditions = append(conditions, "p.module_id = $"+strconv.Itoa(argN))
		args = append(args, *params.ModuleID)
		argN++
	}
	if params.TopicName != "" {
		conditions = append(conditions, "EXISTS (SELECT 1 FROM pdf_topics pt2 JOIN topics t2 ON pt2.topic_id = t2.id WHERE pt2.pdf_id = p.id AND t2.name ILIKE $"+strconv.Itoa(argN)+")")
		args = append(args, "%"+params.TopicName+"%")
		argN++
	}
	if params.SubtopicName != "" {
		conditions = append(conditions, "EXISTS (SELECT 1 FROM pdf_subtopics ps2 JOIN subtopics st2 ON ps2.subtopic_id = st2.id WHERE ps2.pdf_id = p.id AND st2.name ILIKE $"+strconv.Itoa(argN)+")")
		args = append(args, "%"+params.SubtopicName+"%")
		argN++
	}
	if params.TagName != "" {
		conditions = append(conditions, "EXISTS (SELECT 1 FROM pdf_tags ptg2 JOIN tags tg2 ON ptg2.tag_id = tg2.id WHERE ptg2.pdf_id = p.id AND tg2.name ILIKE $"+strconv.Itoa(argN)+")")
		args = append(args, "%"+params.TagName+"%")
		argN++
	}

	whereClause := ""
	for i, c := range conditions {
		if i == 0 {
			whereClause = "WHERE " + c
		} else {
			whereClause += " AND " + c
		}
	}

	countArgs := append([]interface{}{}, args...)
	countQuery := `SELECT COUNT(DISTINCT p.id) FROM pdfs p ` + whereClause
	var total int
	if err := db.Pool.QueryRow(ctx, countQuery, countArgs...).Scan(&total); err != nil {
		return nil, 0, err
	}

	limitArg := strconv.Itoa(argN)
	offsetArg := strconv.Itoa(argN + 1)
	args = append(args, params.Limit, params.Offset)

	query := `
		SELECT p.id, p.storage_path, p.original_filename, p.file_size,
		       p.mime_type, p.module_id, COALESCE(m.name, ''), p.is_active,
		       COALESCE(ARRAY_AGG(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL), '{}'),
		       COALESCE(ARRAY_AGG(DISTINCT st.name) FILTER (WHERE st.name IS NOT NULL), '{}'),
		       COALESCE(ARRAY_AGG(DISTINCT tg.name) FILTER (WHERE tg.name IS NOT NULL), '{}')
		FROM pdfs p
		LEFT JOIN modules m ON p.module_id = m.id
		LEFT JOIN pdf_topics pt ON p.id = pt.pdf_id
		LEFT JOIN topics t ON pt.topic_id = t.id
		LEFT JOIN pdf_subtopics ps ON p.id = ps.pdf_id
		LEFT JOIN subtopics st ON ps.subtopic_id = st.id
		LEFT JOIN pdf_tags ptg ON p.id = ptg.pdf_id
		LEFT JOIN tags tg ON ptg.tag_id = tg.id
		` + whereClause + `
		GROUP BY p.id, m.name
		ORDER BY p.created_at DESC
		LIMIT $` + limitArg + ` OFFSET $` + offsetArg

	rows, err := db.Pool.Query(ctx, query, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var pdfs []PDF
	for rows.Next() {
		var p PDF
		var topicNames, subtopicNames, tagNames []string
		if err := rows.Scan(
			&p.ID, &p.StoragePath, &p.OriginalFilename, &p.FileSize,
			&p.MimeType, &p.ModuleID, &p.ModuleName, &p.IsActive,
			&topicNames, &subtopicNames, &tagNames,
		); err != nil {
			return nil, 0, err
		}
		p.TopicNames = topicNames
		p.SubtopicNames = subtopicNames
		p.TagNames = tagNames
		p.URL = "/api/pdf/" + strconv.Itoa(p.ID)
		pdfs = append(pdfs, p)
	}
	return pdfs, total, rows.Err()
}

func SoftDeletePDF(ctx context.Context, pdfID int) error {
	_, err := db.Pool.Exec(ctx, `UPDATE pdfs SET is_active = false WHERE id = $1`, pdfID)
	return err
}

func HardDeletePDF(ctx context.Context, pdfID int) (string, error) {
	var storagePath string
	err := db.Pool.QueryRow(ctx, `DELETE FROM pdfs WHERE id = $1 RETURNING storage_path`, pdfID).Scan(&storagePath)
	return storagePath, err
}

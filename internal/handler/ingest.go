package handler

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"flashcards-go/internal/config"
	"flashcards-go/internal/db/queries"
	"flashcards-go/internal/security"

	"github.com/rs/zerolog/log"
)

type IngestHandler struct {
	cfg *config.Config
}

func NewIngestHandler(cfg *config.Config) *IngestHandler {
	return &IngestHandler{cfg: cfg}
}

func (h *IngestHandler) APITokenAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var token string

		authHeader := r.Header.Get("Authorization")
		if strings.HasPrefix(strings.ToLower(authHeader), "bearer ") {
			token = strings.TrimPrefix(authHeader, "Bearer ")
			token = strings.TrimPrefix(token, "bearer ")
		} else {
			token = r.Header.Get("X-API-Key")
		}

		if !security.VerifyIngestToken(token, h.cfg.N8NIngestToken) {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": "Unauthorized"})
			return
		}

		next.ServeHTTP(w, r)
	})
}

type IngestFlashcard struct {
	Question    string   `json:"question"`
	Answer      string   `json:"answer"`
	Module      string   `json:"module"`
	Topic       string   `json:"topic"`
	Subtopic    string   `json:"subtopic"`
	Tags        interface{} `json:"tags"`
	Distractors []string `json:"distractors"`
	UserID      string   `json:"user_id"`
	Username    string   `json:"username"`
}

type IngestResult struct {
	Accepted   []map[string]interface{} `json:"accepted"`
	Duplicates []map[string]interface{} `json:"duplicates"`
	Errors     []map[string]interface{} `json:"errors"`
}

func (h *IngestHandler) IngestFlashcards(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	thresholdStr := r.Header.Get("X-Similarity-Threshold")
	threshold := 0.3
	if thresholdStr != "" {
		if t, err := strconv.ParseFloat(thresholdStr, 64); err == nil && t >= 0 && t <= 1 {
			threshold = t
		}
	}

	var payload interface{}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid JSON payload"})
		return
	}

	var flashcards []IngestFlashcard
	switch v := payload.(type) {
	case []interface{}:
		for _, item := range v {
			if fc, ok := item.(map[string]interface{}); ok {
				flashcards = append(flashcards, parseFlashcard(fc))
			}
		}
	case map[string]interface{}:
		if fcs, ok := v["flashcards"].([]interface{}); ok {
			for _, item := range fcs {
				if fc, ok := item.(map[string]interface{}); ok {
					flashcards = append(flashcards, parseFlashcard(fc))
				}
			}
		}
	}

	if len(flashcards) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "No flashcards provided"})
		return
	}

	result := IngestResult{
		Accepted:   []map[string]interface{}{},
		Duplicates: []map[string]interface{}{},
		Errors:     []map[string]interface{}{},
	}

	seenQuestions := make(map[string]bool)

	for i, fc := range flashcards {
		fc.Question = strings.TrimSpace(fc.Question)
		fc.Answer = strings.TrimSpace(fc.Answer)
		fc.Module = strings.TrimSpace(fc.Module)

		if fc.Question == "" || fc.Answer == "" || fc.Module == "" {
			result.Errors = append(result.Errors, map[string]interface{}{
				"index": i,
				"error": "question, answer, and module are required fields",
			})
			continue
		}

		seenKey := strings.ToLower(fc.Module) + "|" + strings.ToLower(fc.Question)
		if seenQuestions[seenKey] {
			result.Duplicates = append(result.Duplicates, map[string]interface{}{
				"index":    i,
				"question": fc.Question,
				"module":   fc.Module,
				"matches":  []map[string]string{{"reason": "duplicate-in-batch"}},
			})
			continue
		}

		moduleID, err := queries.GetModuleIDByName(ctx, fc.Module)
		if err != nil || moduleID == 0 {
			result.Errors = append(result.Errors, map[string]interface{}{
				"index": i,
				"error": "Invalid module: " + fc.Module,
			})
			continue
		}

		duplicates := findDuplicates(ctx, fc.Question, moduleID, threshold)
		if len(duplicates) > 0 {
			result.Duplicates = append(result.Duplicates, map[string]interface{}{
				"index":    i,
				"question": fc.Question,
				"module":   fc.Module,
				"matches":  duplicates,
			})
			continue
		}

		userID := fc.UserID
		if userID == "" {
			userID = h.cfg.N8NDefaultUserID
		}
		username := fc.Username
		if username == "" {
			username = h.cfg.N8NDefaultUsername
		}

		tagsCSV := normalizeTagsToCSV(fc.Tags)
		var topic, subtopic, tags *string
		if fc.Topic != "" {
			t := strings.TrimSpace(fc.Topic)
			topic = &t
		}
		if fc.Subtopic != "" {
			s := strings.TrimSpace(fc.Subtopic)
			subtopic = &s
		}
		if tagsCSV != "" {
			tags = &tagsCSV
		}

		flashcardID, err := queries.InsertSubmittedFlashcard(ctx, userID, username, fc.Question, fc.Answer, fc.Module, topic, subtopic, tags)
		if err != nil {
			result.Errors = append(result.Errors, map[string]interface{}{
				"index": i,
				"error": err.Error(),
			})
			continue
		}

		for j, distractor := range fc.Distractors {
			if j >= h.cfg.NumberOfDistractors {
				break
			}
			distractor = strings.TrimSpace(distractor)
			if distractor != "" {
				questionKey := "flashcard_" + strconv.Itoa(flashcardID)
				queries.InsertSubmittedDistractor(ctx, userID, username, questionKey, distractor)
			}
		}

		seenQuestions[seenKey] = true
		result.Accepted = append(result.Accepted, map[string]interface{}{
			"index":    i,
			"question": fc.Question,
			"module":   fc.Module,
		})
	}

	statusCode := http.StatusCreated
	if len(result.Errors) > 0 || len(result.Duplicates) > 0 {
		statusCode = 207
	}

	writeJSON(w, statusCode, result)
}

func (h *IngestHandler) SubmitDistractors(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var payload map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid JSON payload"})
		return
	}

	var submissions []map[string]interface{}
	if subs, ok := payload["submissions"].([]interface{}); ok {
		for _, s := range subs {
			if sub, ok := s.(map[string]interface{}); ok {
				submissions = append(submissions, sub)
			}
		}
	} else if _, ok := payload["question_id"]; ok {
		submissions = []map[string]interface{}{payload}
	}

	if len(submissions) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "No submissions provided"})
		return
	}

	result := map[string]interface{}{
		"accepted": []map[string]interface{}{},
		"errors":   []map[string]interface{}{},
	}

	for i, sub := range submissions {
		questionID, _ := sub["question_id"].(string)
		distractors, _ := sub["distractors"].([]interface{})
		userID, _ := sub["user_id"].(string)
		username, _ := sub["username"].(string)

		if questionID == "" {
			result["errors"] = append(result["errors"].([]map[string]interface{}), map[string]interface{}{
				"index": i,
				"error": "question_id is required",
			})
			continue
		}

		if userID == "" {
			userID = h.cfg.N8NDefaultUserID
		}
		if username == "" {
			username = h.cfg.N8NDefaultUsername
		}

		question, _ := queries.GetQuestionByID(ctx, questionID)
		if question == nil {
			result["errors"] = append(result["errors"].([]map[string]interface{}), map[string]interface{}{
				"index": i,
				"error": "Question not found: " + questionID,
			})
			continue
		}

		count := 0
		for j, d := range distractors {
			if j >= h.cfg.NumberOfDistractors {
				break
			}
			text, _ := d.(string)
			text = strings.TrimSpace(text)
			if text != "" {
				if err := queries.InsertSubmittedDistractor(ctx, userID, username, questionID, text); err == nil {
					count++
				}
			}
		}

		if count == 0 {
			result["errors"] = append(result["errors"].([]map[string]interface{}), map[string]interface{}{
				"index": i,
				"error": "At least one non-empty distractor is required",
			})
			continue
		}

		result["accepted"] = append(result["accepted"].([]map[string]interface{}), map[string]interface{}{
			"index":       i,
			"question_id": questionID,
			"count":       count,
		})
	}

	statusCode := http.StatusCreated
	if len(result["errors"].([]map[string]interface{})) > 0 {
		statusCode = 207
	}

	writeJSON(w, statusCode, result)
}

func (h *IngestHandler) CheckDuplicates(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	thresholdStr := r.Header.Get("X-Similarity-Threshold")
	threshold := 0.3
	if thresholdStr != "" {
		if t, err := strconv.ParseFloat(thresholdStr, 64); err == nil && t >= 0 && t <= 1 {
			threshold = t
		}
	}

	var req struct {
		Question string `json:"question"`
		Module   string `json:"module"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	req.Question = strings.TrimSpace(req.Question)
	req.Module = strings.TrimSpace(req.Module)

	if req.Question == "" || req.Module == "" || len(req.Question) < 10 {
		writeJSON(w, http.StatusOK, map[string]interface{}{"duplicates": []interface{}{}})
		return
	}

	moduleID, err := queries.GetModuleIDByName(ctx, req.Module)
	if err != nil || moduleID == 0 {
		writeJSON(w, http.StatusOK, map[string]interface{}{"duplicates": []interface{}{}})
		return
	}

	duplicates := findDuplicates(ctx, req.Question, moduleID, threshold)
	writeJSON(w, http.StatusOK, map[string]interface{}{"duplicates": duplicates})
}

func (h *IngestHandler) ApproveFlashcard(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req struct {
		SubmissionID int      `json:"submission_id"`
		Question     string   `json:"question"`
		Answer       string   `json:"answer"`
		Module       string   `json:"module"`
		Topic        string   `json:"topic"`
		Subtopic     string   `json:"subtopic"`
		Tags         []string `json:"tags"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.SubmissionID == 0 || req.Question == "" || req.Answer == "" || req.Module == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "submission_id, question, answer, and module are required"})
		return
	}

	moduleID, err := queries.GetModuleIDByName(ctx, req.Module)
	if err != nil || moduleID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid module specified"})
		return
	}

	var topic, subtopic *string
	if req.Topic != "" {
		topic = &req.Topic
	}
	if req.Subtopic != "" {
		subtopic = &req.Subtopic
	}

	result, err := queries.ApproveFlashcard(ctx, req.SubmissionID, req.Question, req.Answer, moduleID, topic, subtopic, req.Tags)
	if err != nil {
		log.Error().Err(err).Msg("Failed to approve flashcard")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Error approving flashcard: " + err.Error()})
		return
	}

	if !result.Success {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Error approving flashcard: " + result.Error})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":                   true,
		"message":                   "Flashcard approved and added to the database.",
		"question_id":               result.QuestionID,
		"pending_distractors_count": result.PendingDistractorsCount,
	})
}

func (h *IngestHandler) RejectFlashcard(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req struct {
		SubmissionID int `json:"submission_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.SubmissionID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "submission_id is required"})
		return
	}

	rejectedCount, err := queries.RejectFlashcard(ctx, req.SubmissionID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to reject flashcard")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Error rejecting flashcard: " + err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":                    true,
		"message":                    "Flashcard submission rejected and removed.",
		"rejected_distractors_count": rejectedCount,
	})
}

func (h *IngestHandler) ApproveDistractor(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req struct {
		SubmissionID int `json:"submission_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.SubmissionID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "submission_id is required"})
		return
	}

	distractorID, err := queries.ApproveDistractor(ctx, req.SubmissionID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to approve distractor")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Error approving distractor: " + err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":       true,
		"message":       "Distractor approved and added to the database.",
		"distractor_id": distractorID,
	})
}

func (h *IngestHandler) RejectDistractor(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req struct {
		SubmissionID int `json:"submission_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.SubmissionID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "submission_id is required"})
		return
	}

	if err := queries.RejectDistractor(ctx, req.SubmissionID); err != nil {
		log.Error().Err(err).Msg("Failed to reject distractor")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Error rejecting distractor: " + err.Error()})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "Distractor submission rejected and removed.",
	})
}

func parseFlashcard(m map[string]interface{}) IngestFlashcard {
	fc := IngestFlashcard{}
	if v, ok := m["question"].(string); ok {
		fc.Question = v
	}
	if v, ok := m["answer"].(string); ok {
		fc.Answer = v
	}
	if v, ok := m["module"].(string); ok {
		fc.Module = v
	}
	if v, ok := m["topic"].(string); ok {
		fc.Topic = v
	}
	if v, ok := m["subtopic"].(string); ok {
		fc.Subtopic = v
	} else if v, ok := m["sub_topic"].(string); ok {
		fc.Subtopic = v
	} else if v, ok := m["sub-topic"].(string); ok {
		fc.Subtopic = v
	}
	fc.Tags = m["tags"]
	if v, ok := m["distractors"].([]interface{}); ok {
		for _, d := range v {
			if s, ok := d.(string); ok {
				fc.Distractors = append(fc.Distractors, s)
			}
		}
	}
	if v, ok := m["user_id"].(string); ok {
		fc.UserID = v
	}
	if v, ok := m["username"].(string); ok {
		fc.Username = v
	}
	return fc
}

func normalizeTagsToCSV(tags interface{}) string {
	switch v := tags.(type) {
	case string:
		return strings.TrimSpace(v)
	case []interface{}:
		var parts []string
		for _, t := range v {
			if s, ok := t.(string); ok {
				s = strings.TrimSpace(s)
				if s != "" {
					parts = append(parts, s)
				}
			}
		}
		return strings.Join(parts, ", ")
	case []string:
		var parts []string
		for _, s := range v {
			s = strings.TrimSpace(s)
			if s != "" {
				parts = append(parts, s)
			}
		}
		return strings.Join(parts, ", ")
	}
	return ""
}

func findDuplicates(ctx context.Context, question string, moduleID int, threshold float64) []map[string]interface{} {
	return FindDuplicates(ctx, question, moduleID, threshold)
}

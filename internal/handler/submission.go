package handler

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"flashcards-go/internal/auth"
	"flashcards-go/internal/config"
	"flashcards-go/internal/db/queries"

	"github.com/rs/zerolog/log"
)

type SubmissionHandler struct {
	cfg *config.Config
}

func NewSubmissionHandler(cfg *config.Config) *SubmissionHandler {
	return &SubmissionHandler{cfg: cfg}
}

type SubmitFlashcardRequest struct {
	Question   string   `json:"question"`
	Answer     string   `json:"answer"`
	Module     string   `json:"module"`
	Topic      string   `json:"topic"`
	Subtopic   string   `json:"subtopic"`
	Tags       string   `json:"tags"`
	Distractors []string `json:"distractors"`
}

func (h *SubmissionHandler) SubmitFlashcard(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)
	username := auth.GetUsername(ctx)

	var req SubmitFlashcardRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	req.Question = strings.TrimSpace(req.Question)
	req.Answer = strings.TrimSpace(req.Answer)
	req.Module = strings.TrimSpace(req.Module)
	req.Topic = strings.TrimSpace(req.Topic)
	req.Subtopic = strings.TrimSpace(req.Subtopic)
	req.Tags = strings.TrimSpace(req.Tags)

	if req.Question == "" || req.Answer == "" || req.Module == "" || req.Topic == "" || req.Subtopic == "" || req.Tags == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Please fill in all required fields"})
		return
	}

	var topic, subtopic, tags *string
	if req.Topic != "" {
		topic = &req.Topic
	}
	if req.Subtopic != "" {
		subtopic = &req.Subtopic
	}
	if req.Tags != "" {
		tags = &req.Tags
	}

	flashcardID, err := queries.InsertSubmittedFlashcard(ctx, userID, username, req.Question, req.Answer, req.Module, topic, subtopic, tags)
	if err != nil {
		log.Error().Err(err).Msg("Failed to insert flashcard")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to submit flashcard"})
		return
	}

	distractorCount := 0
	for i, distractor := range req.Distractors {
		if i >= h.cfg.NumberOfDistractors {
			break
		}
		distractor = strings.TrimSpace(distractor)
		if distractor != "" {
			questionKey := "flashcard_" + strconv.Itoa(flashcardID)
			if err := queries.InsertSubmittedDistractor(ctx, userID, username, questionKey, distractor); err != nil {
				log.Error().Err(err).Msg("Failed to insert distractor")
			} else {
				distractorCount++
			}
		}
	}

	message := "Flashcard submitted for review! Thank you."
	if distractorCount > 0 {
		message = "Flashcard and distractors submitted for review! Thank you."
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": message,
	})
}

type SubmitDistractorRequest struct {
	QuestionID  string   `json:"question_id"`
	Distractors []string `json:"distractors"`
}

func (h *SubmissionHandler) SubmitDistractor(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)
	username := auth.GetUsername(ctx)

	var req SubmitDistractorRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.QuestionID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Question ID required"})
		return
	}

	count := 0
	for i, distractor := range req.Distractors {
		if i >= h.cfg.NumberOfDistractors {
			break
		}
		distractor = strings.TrimSpace(distractor)
		if distractor != "" {
			if err := queries.InsertSubmittedDistractor(ctx, userID, username, req.QuestionID, distractor); err != nil {
				log.Error().Err(err).Msg("Failed to insert distractor")
			} else {
				count++
			}
		}
	}

	if count == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Please provide at least one distractor"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "Distractors submitted for review! Thank you.",
	})
}

type ReportQuestionRequest struct {
	Question    string  `json:"question"`
	QuestionID  *string `json:"question_id"`
	Message     string  `json:"message"`
	Distractors string  `json:"distractors"`
}

func (h *SubmissionHandler) ReportQuestion(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)
	username := auth.GetUsername(ctx)

	var req ReportQuestionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	var message, distractors *string
	if req.Message != "" {
		message = &req.Message
	}
	if req.Distractors != "" {
		distractors = &req.Distractors
	}

	if err := queries.InsertReportedQuestion(ctx, userID, username, req.Question, req.QuestionID, message, distractors); err != nil {
		log.Error().Err(err).Msg("Failed to insert report")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to submit report"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "Your report has been submitted!",
	})
}

type RequestPDFAccessRequest struct {
	Message string `json:"message"`
}

func (h *SubmissionHandler) RequestPDFAccess(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)
	username := auth.GetUsername(ctx)

	var req RequestPDFAccessRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	var message *string
	if req.Message != "" {
		message = &req.Message
	}

	if err := queries.InsertPDFAccessRequest(ctx, userID, username, message); err != nil {
		log.Error().Err(err).Msg("Failed to insert PDF access request")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to submit request"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "Your request has been submitted!",
	})
}

type CheckDuplicatesRequest struct {
	Question string `json:"question"`
	Module   string `json:"module"`
}

func (h *SubmissionHandler) CheckDuplicates(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req CheckDuplicatesRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	req.Question = strings.TrimSpace(req.Question)
	req.Module = strings.TrimSpace(req.Module)

	if len(req.Question) < 10 || req.Module == "" {
		writeJSON(w, http.StatusOK, map[string]interface{}{"matches": []interface{}{}})
		return
	}

	moduleID, err := queries.GetModuleIDByName(ctx, req.Module)
	if err != nil || moduleID == 0 {
		writeJSON(w, http.StatusOK, map[string]interface{}{"matches": []interface{}{}})
		return
	}

	threshold := 0.3
	if t := r.Header.Get("X-Similarity-Threshold"); t != "" {
		if parsed, err := strconv.ParseFloat(t, 64); err == nil && parsed > 0 && parsed < 1 {
			threshold = parsed
		}
	}

	matches := FindDuplicates(ctx, req.Question, moduleID, threshold)
	if matches == nil {
		matches = []map[string]interface{}{}
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{"matches": matches})
}

// --- Suggestion endpoints ---

type SuggestRequest struct {
	Module   string `json:"module"`
	Topic    string `json:"topic"`
	Subtopic string `json:"subtopic"`
	Query    string `json:"query"`
}

func (h *SubmissionHandler) SuggestTopics(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req SuggestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}
	if req.Module == "" {
		writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": []interface{}{}})
		return
	}
	moduleID, err := queries.GetModuleIDByName(ctx, req.Module)
	if err != nil || moduleID == 0 {
		writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": []interface{}{}})
		return
	}
	suggestions, err := queries.GetTopicSuggestions(ctx, moduleID, strings.ToLower(strings.TrimSpace(req.Query)))
	if err != nil {
		log.Error().Err(err).Msg("Failed to get topic suggestions")
		writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": []interface{}{}})
		return
	}
	if suggestions == nil {
		suggestions = []queries.Suggestion{}
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": suggestions})
}

func (h *SubmissionHandler) SuggestSubtopics(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req SuggestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}
	if req.Module == "" {
		writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": []interface{}{}})
		return
	}
	moduleID, err := queries.GetModuleIDByName(ctx, req.Module)
	if err != nil || moduleID == 0 {
		writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": []interface{}{}})
		return
	}
	suggestions, err := queries.GetSubtopicSuggestions(ctx, moduleID, strings.TrimSpace(req.Topic), strings.ToLower(strings.TrimSpace(req.Query)))
	if err != nil {
		log.Error().Err(err).Msg("Failed to get subtopic suggestions")
		writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": []interface{}{}})
		return
	}
	if suggestions == nil {
		suggestions = []queries.Suggestion{}
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": suggestions})
}

func (h *SubmissionHandler) SuggestTags(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req SuggestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}
	if req.Module == "" {
		writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": []interface{}{}})
		return
	}
	moduleID, err := queries.GetModuleIDByName(ctx, req.Module)
	if err != nil || moduleID == 0 {
		writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": []interface{}{}})
		return
	}
	suggestions, err := queries.GetTagSuggestions(ctx, moduleID, strings.ToLower(strings.TrimSpace(req.Query)))
	if err != nil {
		log.Error().Err(err).Msg("Failed to get tag suggestions")
		writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": []interface{}{}})
		return
	}
	if suggestions == nil {
		suggestions = []queries.Suggestion{}
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"suggestions": suggestions})
}

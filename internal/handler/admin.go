package handler

import (
	"encoding/json"
	"net/http"
	"strings"

	"flashcards-go/internal/auth"
	"flashcards-go/internal/config"
	"flashcards-go/internal/db/queries"

	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog/log"
)

type AdminHandler struct {
	cfg *config.Config
}

func NewAdminHandler(cfg *config.Config) *AdminHandler {
	return &AdminHandler{cfg: cfg}
}

func (h *AdminHandler) GetSubmissions(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	flashcards, err := queries.GetSubmittedFlashcards(ctx)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get flashcards")
		flashcards = nil
	}

	distractors, err := queries.GetSubmittedDistractors(ctx)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get distractors")
		distractors = nil
	}

	reports, err := queries.GetReportedQuestions(ctx)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get reports")
		reports = nil
	}

	pdfRequests, err := queries.GetPDFAccessRequests(ctx)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get PDF requests")
		pdfRequests = nil
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"flashcards":   flashcards,
		"distractors":  distractors,
		"reports":      reports,
		"pdf_requests": pdfRequests,
	})
}

type ApproveFlashcardRequest struct {
	SubmissionID int      `json:"submission_id"`
	Question     string   `json:"question"`
	Answer       string   `json:"answer"`
	Module       string   `json:"module"`
	Topic        string   `json:"topic"`
	Subtopic     string   `json:"subtopic"`
	Tags         []string `json:"tags"`
}

func (h *AdminHandler) ApproveFlashcard(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req ApproveFlashcardRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	req.Question = strings.TrimSpace(req.Question)
	req.Answer = strings.TrimSpace(req.Answer)
	req.Module = strings.TrimSpace(req.Module)

	if req.SubmissionID == 0 || req.Question == "" || req.Answer == "" || req.Module == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing required fields"})
		return
	}

	moduleID, err := queries.GetModuleIDByName(ctx, req.Module)
	if err != nil || moduleID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid module"})
		return
	}

	var topic, subtopic *string
	if req.Topic != "" {
		t := strings.TrimSpace(req.Topic)
		topic = &t
	}
	if req.Subtopic != "" {
		s := strings.TrimSpace(req.Subtopic)
		subtopic = &s
	}

	result, err := queries.ApproveFlashcard(ctx, req.SubmissionID, req.Question, req.Answer, moduleID, topic, subtopic, req.Tags)
	if err != nil {
		log.Error().Err(err).Msg("Failed to approve flashcard")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to approve flashcard"})
		return
	}

	if !result.Success {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": result.Error})
		return
	}

	writeJSON(w, http.StatusOK, result)
}

type RejectFlashcardRequest struct {
	SubmissionID int `json:"submission_id"`
}

func (h *AdminHandler) RejectFlashcard(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req RejectFlashcardRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.SubmissionID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing submission_id"})
		return
	}

	rejectedCount, err := queries.RejectFlashcard(ctx, req.SubmissionID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to reject flashcard")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to reject flashcard"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":                    true,
		"rejected_distractors_count": rejectedCount,
	})
}

type ApproveDistractorRequest struct {
	SubmissionID int `json:"submission_id"`
}

func (h *AdminHandler) ApproveDistractor(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req ApproveDistractorRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.SubmissionID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing submission_id"})
		return
	}

	distractorID, err := queries.ApproveDistractor(ctx, req.SubmissionID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to approve distractor")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to approve distractor"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":       true,
		"distractor_id": distractorID,
	})
}

type RejectDistractorRequest struct {
	SubmissionID int `json:"submission_id"`
}

func (h *AdminHandler) RejectDistractor(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req RejectDistractorRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.SubmissionID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing submission_id"})
		return
	}

	if err := queries.RejectDistractor(ctx, req.SubmissionID); err != nil {
		log.Error().Err(err).Msg("Failed to reject distractor")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to reject distractor"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
	})
}

type DiscardReportRequest struct {
	ReportID int `json:"report_id"`
}

func (h *AdminHandler) DiscardReport(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req DiscardReportRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.ReportID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing report_id"})
		return
	}

	if err := queries.DeleteReportedQuestion(ctx, req.ReportID); err != nil {
		log.Error().Err(err).Msg("Failed to discard report")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to discard report"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
	})
}

type ApprovePDFAccessRequest struct {
	RequestID int `json:"request_id"`
}

func (h *AdminHandler) ApprovePDFAccess(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req ApprovePDFAccessRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.RequestID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing request_id"})
		return
	}

	pdfRequests, err := queries.GetPDFAccessRequests(ctx)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get PDF requests")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to process request"})
		return
	}

	var discordID string
	for _, pr := range pdfRequests {
		if pr.ID == req.RequestID {
			discordID = pr.DiscordID
			break
		}
	}

	if discordID == "" {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "Request not found"})
		return
	}

	if err := auth.GrantPDFAccess(ctx, discordID); err != nil {
		log.Error().Err(err).Msg("Failed to grant PDF access")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to grant PDF access"})
		return
	}

	if err := queries.DeletePDFAccessRequest(ctx, req.RequestID); err != nil {
		log.Error().Err(err).Msg("Failed to delete PDF request")
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
	})
}

type DenyPDFAccessRequest struct {
	RequestID int `json:"request_id"`
}

func (h *AdminHandler) DenyPDFAccess(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req DenyPDFAccessRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.RequestID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing request_id"})
		return
	}

	if err := queries.DeletePDFAccessRequest(ctx, req.RequestID); err != nil {
		log.Error().Err(err).Msg("Failed to delete PDF request")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to deny request"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
	})
}

// GetQuestionForReport returns the current live state of a question + its manual distractors.
func (h *AdminHandler) GetQuestionForReport(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	questionID := chi.URLParam(r, "questionID")
	if questionID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing question ID"})
		return
	}

	q, err := queries.GetLiveQuestion(ctx, questionID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get question")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to get question"})
		return
	}
	if q == nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "Question not found"})
		return
	}

	distractors, err := queries.GetManualDistractorsForQuestion(ctx, questionID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get manual distractors")
		distractors = nil
	}
	if distractors == nil {
		distractors = []queries.LiveManualDistractor{}
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"question":    q,
		"distractors": distractors,
	})
}

type ResolveReportDistractorEdit struct {
	ID      int    `json:"id"`
	Type    string `json:"type"`
	NewText string `json:"new_text"`
	Delete  bool   `json:"delete"`
}

type ResolveReportRequest struct {
	ReportID          int                           `json:"report_id"`
	QuestionID        string                        `json:"question_id"`
	NewQuestionText   string                        `json:"new_question_text"`
	NewQuestionAnswer string                        `json:"new_question_answer"`
	DeleteQuestion    bool                          `json:"delete_question"`
	Distractors       []ResolveReportDistractorEdit `json:"distractors"`
}

func (h *AdminHandler) ResolveReport(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req ResolveReportRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}
	if req.ReportID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing report_id"})
		return
	}

	if req.QuestionID != "" {
		if req.DeleteQuestion {
			if err := queries.DeleteQuestion(ctx, req.QuestionID); err != nil {
				log.Error().Err(err).Msg("Failed to delete question")
				writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to delete question"})
				return
			}
		} else {
			if req.NewQuestionText != "" {
				if err := queries.UpdateQuestionText(ctx, req.QuestionID, req.NewQuestionText); err != nil {
					log.Error().Err(err).Msg("Failed to update question text")
				}
			}
			if req.NewQuestionAnswer != "" {
				if err := queries.UpdateQuestionAnswer(ctx, req.QuestionID, req.NewQuestionAnswer); err != nil {
					log.Error().Err(err).Msg("Failed to update question answer")
				}
			}
		}
	}

	for _, d := range req.Distractors {
		if d.Type == "manual_distractor" {
			if d.Delete {
				if err := queries.DeleteManualDistractorByID(ctx, d.ID); err != nil {
					log.Error().Err(err).Int("id", d.ID).Msg("Failed to delete manual distractor")
				}
			} else if d.NewText != "" {
				if err := queries.UpdateManualDistractor(ctx, d.ID, d.NewText); err != nil {
					log.Error().Err(err).Int("id", d.ID).Msg("Failed to update manual distractor")
				}
			}
		}
	}

	if err := queries.DeleteReportedQuestion(ctx, req.ReportID); err != nil {
		log.Error().Err(err).Msg("Failed to delete report")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to discard report"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{"success": true})
}

type EditAnswerRequest struct {
	QuestionID          string `json:"question_id"`
	ManualDistractorID  int    `json:"manual_distractor_id"`
	NewText             string `json:"new_text"`
	EditType            string `json:"edit_type"`
}

func (h *AdminHandler) EditAnswer(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req EditAnswerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.NewText == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing new_text"})
		return
	}

	var err error
	if req.EditType == "manual_distractor" && req.ManualDistractorID > 0 {
		err = queries.UpdateManualDistractor(ctx, req.ManualDistractorID, req.NewText)
	} else if req.QuestionID != "" {
		err = queries.UpdateQuestionAnswer(ctx, req.QuestionID, req.NewText)
	} else {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid edit type or missing ID"})
		return
	}

	if err != nil {
		log.Error().Err(err).Msg("Failed to edit answer")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to edit answer"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
	})
}

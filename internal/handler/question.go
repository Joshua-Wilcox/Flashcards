package handler

import (
	"context"
	"encoding/json"
	"math/rand"
	"net/http"
	"time"

	"flashcards-go/internal/auth"
	"flashcards-go/internal/config"
	"flashcards-go/internal/db/queries"
	"flashcards-go/internal/realtime"
	"flashcards-go/internal/security"

	"github.com/rs/zerolog/log"
	"golang.org/x/sync/errgroup"
)

type QuestionHandler struct {
	cfg *config.Config
	hub *realtime.Hub
}

func NewQuestionHandler(cfg *config.Config, hub *realtime.Hub) *QuestionHandler {
	h := &QuestionHandler{cfg: cfg, hub: hub}
	
	// Register the prefetch function
	security.SetPrefetchFunc(h.prefetchQuestion)
	
	return h
}

type GetQuestionRequest struct {
	Module     string   `json:"module"`
	Topics     []string `json:"topics"`
	Subtopics  []string `json:"subtopics"`
	Tags       []string `json:"tags"`
	QuestionID string   `json:"question_id,omitempty"`
}

type GetQuestionResponse struct {
	Question       string        `json:"question"`
	Answers        []string      `json:"answers"`
	AnswerIDs      []string      `json:"answer_ids"`
	AnswerTypes    []string      `json:"answer_types"`
	AnswerMetadata []*int        `json:"answer_metadata"`
	Module         string        `json:"module"`
	Topic          string        `json:"topic"`
	Subtopic       string        `json:"subtopic"`
	Tags           []string      `json:"tags"`
	PDFs           []queries.PDF `json:"pdfs"`
	QuestionID     string        `json:"question_id"`
	Token          string        `json:"token"`
	IsAdmin        bool          `json:"is_admin"`
	FiltersApplied bool          `json:"filters_applied"`
	FiltersRelaxed bool          `json:"filters_relaxed"`
	TotalFiltered  int           `json:"total_filtered_questions"`
	Error          string        `json:"error,omitempty"`
}

func (h *QuestionHandler) GetQuestion(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)
	isAdmin := auth.GetIsAdmin(ctx)

	var req GetQuestionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.Module == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Module is required"})
		return
	}

	moduleID, err := queries.GetModuleIDByName(ctx, req.Module)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get module ID")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal error"})
		return
	}
	if moduleID == 0 {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "Module not found"})
		return
	}

	// Try to get a prefetched question first (fast path)
	var prefetched *security.PrefetchedQuestion
	if req.QuestionID == "" {
		queue := security.GetUserQueue(userID)
		if queue != nil && queue.ModuleID == moduleID {
			prefetched = queue.Pop()
		}
	}

	var resp GetQuestionResponse

	if prefetched != nil {
		// Fast path: use prefetched question
		token := security.GenerateSignedToken(prefetched.QuestionID, userID)
		security.CacheAnswer(token, prefetched.QuestionID, prefetched.Answer, moduleID)

		// Get PDFs in background or skip for speed
		var pdfs []queries.PDF
		pdfs, _ = queries.GetPDFsForQuestion(ctx, prefetched.QuestionID, 3)

		resp = GetQuestionResponse{
			Question:       prefetched.Question,
			Answers:        prefetched.Answers,
			AnswerIDs:      prefetched.AnswerIDs,
			AnswerTypes:    prefetched.AnswerTypes,
			AnswerMetadata: prefetched.AnswerMetadata,
			Module:         req.Module,
			Topic:          joinStrings(prefetched.Topics),
			Subtopic:       joinStrings(prefetched.Subtopics),
			Tags:           prefetched.Tags,
			PDFs:           pdfs,
			QuestionID:     prefetched.QuestionID,
			Token:          token,
			IsAdmin:        isAdmin,
			FiltersApplied: len(req.Topics) > 0 || len(req.Subtopics) > 0 || len(req.Tags) > 0,
			FiltersRelaxed: false,
			TotalFiltered:  1,
		}

		// Trigger background prefetch to refill queue
		security.TriggerPrefetch(userID, moduleID, req.Topics, req.Subtopics, req.Tags)

	} else {
		// Slow path: fetch from database
		question, answers, answerIDs, answerTypes, answerMetadata, err := h.fetchQuestionWithDistractors(ctx, moduleID, req.Topics, req.Subtopics, req.Tags, req.QuestionID, nil)
		if err != nil {
			log.Error().Err(err).Msg("Failed to get question")
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal error"})
			return
		}

		if question == nil {
			writeJSON(w, http.StatusOK, map[string]string{"error": "No questions found matching the criteria."})
			return
		}

		token := security.GenerateSignedToken(question.ID, userID)
		security.CacheAnswer(token, question.ID, question.Answer, moduleID)

		pdfs, _ := queries.GetPDFsForQuestion(ctx, question.ID, 3)

		resp = GetQuestionResponse{
			Question:       question.Question,
			Answers:        answers,
			AnswerIDs:      answerIDs,
			AnswerTypes:    answerTypes,
			AnswerMetadata: answerMetadata,
			Module:         req.Module,
			Topic:          joinStrings(question.Topics),
			Subtopic:       joinStrings(question.Subtopics),
			Tags:           question.Tags,
			PDFs:           pdfs,
			QuestionID:     question.ID,
			Token:          token,
			IsAdmin:        isAdmin,
			FiltersApplied: len(req.Topics) > 0 || len(req.Subtopics) > 0 || len(req.Tags) > 0,
			FiltersRelaxed: false,
			TotalFiltered:  1,
		}

		// Start prefetching for next questions
		security.TriggerPrefetch(userID, moduleID, req.Topics, req.Subtopics, req.Tags)
	}

	writeJSON(w, http.StatusOK, resp)
}

func (h *QuestionHandler) fetchQuestionWithDistractors(ctx context.Context, moduleID int, topics, subtopics, tags []string, specificID string, excludeIDs []string) (*queries.Question, []string, []string, []string, []*int, error) {
	var question *queries.Question
	var manualDistractors, smartDistractors []queries.Distractor

	g, gctx := errgroup.WithContext(ctx)

	g.Go(func() error {
		var err error
		question, err = queries.GetRandomQuestionExcluding(gctx, moduleID, topics, subtopics, tags, specificID, excludeIDs)
		return err
	})

	if err := g.Wait(); err != nil {
		return nil, nil, nil, nil, nil, err
	}

	if question == nil {
		return nil, nil, nil, nil, nil, nil
	}

	g2, gctx2 := errgroup.WithContext(ctx)

	g2.Go(func() error {
		var err error
		manualDistractors, err = queries.GetManualDistractors(gctx2, question.ID, h.cfg.NumberOfDistractors)
		return err
	})

	g2.Go(func() error {
		var err error
		smartDistractors, err = queries.GetSmartDistractors(gctx2, question.ID, moduleID, question.Topics, question.Subtopics, question.Tags, h.cfg.NumberOfDistractors)
		return err
	})

	if err := g2.Wait(); err != nil {
		return nil, nil, nil, nil, nil, err
	}

	var allDistractors []queries.Distractor
	allDistractors = append(allDistractors, manualDistractors...)
	allDistractors = append(allDistractors, smartDistractors...)

	if len(allDistractors) > h.cfg.NumberOfDistractors {
		allDistractors = allDistractors[:h.cfg.NumberOfDistractors]
	}

	answers := []string{question.Answer}
	answerIDs := []string{question.ID}
	answerTypes := []string{"question"}
	answerMetadata := []*int{nil}

	for _, d := range allDistractors {
		answers = append(answers, d.Answer)
		answerIDs = append(answerIDs, d.ID)
		answerTypes = append(answerTypes, d.Type)
		answerMetadata = append(answerMetadata, d.Metadata)
	}

	shuffleAnswers(answers, answerIDs, answerTypes, answerMetadata)

	return question, answers, answerIDs, answerTypes, answerMetadata, nil
}

func (h *QuestionHandler) prefetchQuestion(ctx context.Context, userID string, moduleID int, topics, subtopics, tags []string, excludeIDs []string) (*security.PrefetchedQuestion, error) {
	question, answers, answerIDs, answerTypes, answerMetadata, err := h.fetchQuestionWithDistractors(ctx, moduleID, topics, subtopics, tags, "", excludeIDs)
	if err != nil || question == nil {
		return nil, err
	}

	return &security.PrefetchedQuestion{
		QuestionID:     question.ID,
		Question:       question.Question,
		Answer:         question.Answer,
		ModuleID:       moduleID,
		Topics:         question.Topics,
		Subtopics:      question.Subtopics,
		Tags:           question.Tags,
		Answers:        answers,
		AnswerIDs:      answerIDs,
		AnswerTypes:    answerTypes,
		AnswerMetadata: answerMetadata,
	}, nil
}

type CheckAnswerRequest struct {
	Answer string `json:"answer"`
	Token  string `json:"token"`
}

type CheckAnswerResponse struct {
	Correct bool   `json:"correct"`
	Error   string `json:"error,omitempty"`
}

func (h *QuestionHandler) CheckAnswer(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)
	username := auth.GetUsername(ctx)

	var req CheckAnswerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request"})
		return
	}

	if req.Token == "" || req.Answer == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Missing token or answer"})
		return
	}

	questionID, valid := security.VerifySignedToken(req.Token, userID)
	if !valid {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid or expired token"})
		return
	}

	// Try to get answer from cache first (fast path - no DB query)
	cached := security.GetCachedAnswer(req.Token)

	var isCorrect bool
	var moduleID int

	if cached != nil {
		// Fast path: answer is cached
		isCorrect = req.Answer == cached.CorrectAnswer
		moduleID = cached.ModuleID
	} else {
		// Slow path: need to query DB (shouldn't happen often)
		question, err := queries.GetQuestionByID(ctx, questionID)
		if err != nil || question == nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Question not found"})
			return
		}
		isCorrect = req.Answer == question.Answer
		moduleID = question.ModuleID
	}

	// Only update stats on correct answer (and only once per token)
	if isCorrect {
		// Check if token already used
		used, err := queries.IsTokenUsed(ctx, userID, req.Token)
		if err != nil {
			log.Error().Err(err).Msg("Failed to check token")
		}

		if !used {
			// Update stats in background - don't block the response
			go func() {
				bgCtx := context.Background()
				result, _, err := queries.ProcessAnswerCheck(bgCtx, userID, questionID, req.Answer, req.Token, username)
				if err != nil {
					log.Error().Err(err).Msg("Failed to process answer stats")
					return
				}

				// Get module name for broadcast
				mn, _ := queries.GetModuleNameByID(bgCtx, moduleID)

				// Get approved cards count for leaderboard
				userStats, _ := queries.GetUserStats(bgCtx, userID)
				approvedCards := 0
				if userStats != nil {
					approvedCards = userStats.ApprovedCards
				}

				if h.hub != nil && result != nil {
					h.hub.BroadcastActivity(realtime.ActivityEvent{
						UserID:     userID,
						Username:   username,
						ModuleName: mn,
						Streak:     result.ModuleStreak,
					})

					h.hub.BroadcastLeaderboardUpdate(realtime.LeaderboardUpdate{
						UserID:         userID,
						Username:       username,
						ModuleID:       moduleID,
						CorrectAnswers: result.TotalCorrect,
						TotalAnswers:   result.TotalAnswers,
						CurrentStreak:  result.NewStreak,
						MaxStreak:      result.MaxStreak,
						ApprovedCards:  approvedCards,
						LastAnswerTime: time.Now().Format(time.RFC3339),
					})
				}
			}()
		}

		// Clean up cache entry
		security.DeleteCachedAnswer(req.Token)
	} else {
		// Wrong answer - reset streak in background
		go func() {
			if err := queries.ResetUserStreak(context.Background(), userID, moduleID); err != nil {
				log.Error().Err(err).Msg("Failed to reset streak")
			}
		}()
	}

	writeJSON(w, http.StatusOK, CheckAnswerResponse{Correct: isCorrect})
}

func shuffleAnswers(answers []string, ids []string, types []string, metadata []*int) {
	n := len(answers)
	for i := n - 1; i > 0; i-- {
		j := rand.Intn(i + 1)
		answers[i], answers[j] = answers[j], answers[i]
		ids[i], ids[j] = ids[j], ids[i]
		types[i], types[j] = types[j], types[i]
		metadata[i], metadata[j] = metadata[j], metadata[i]
	}
}

func joinStrings(s []string) string {
	if len(s) == 0 {
		return ""
	}
	result := s[0]
	for i := 1; i < len(s); i++ {
		result += ", " + s[i]
	}
	return result
}

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

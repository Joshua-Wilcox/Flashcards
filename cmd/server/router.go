package main

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"flashcards-go/internal/auth"
	"flashcards-go/internal/config"
	"flashcards-go/internal/db"
	"flashcards-go/internal/handler"
	"flashcards-go/internal/realtime"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
)

var wsHub *realtime.Hub

func setupRouter(cfg *config.Config) *chi.Mux {
	r := chi.NewRouter()

	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Compress(5))

	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   []string{"http://localhost:*", "http://127.0.0.1:*", "https://flashcards.josh.software"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-CSRF-Token", "X-API-Key", "X-Similarity-Threshold"},
		ExposedHeaders:   []string{"Link"},
		AllowCredentials: true,
		MaxAge:           300,
	}))

	r.Use(auth.EnforceSessionVersion(cfg))

	wsHub = realtime.NewHub()
	go wsHub.Run()

	authHandler := handler.NewAuthHandler(cfg)
	questionHandler := handler.NewQuestionHandler(cfg, wsHub)
	filterHandler := handler.NewFilterHandler()
	userHandler := handler.NewUserHandler()
	submissionHandler := handler.NewSubmissionHandler(cfg)
	adminHandler := handler.NewAdminHandler(cfg)
	ingestHandler := handler.NewIngestHandler(cfg)
	pdfHandler := handler.NewPDFHandler(cfg)
	paymentsHandler := handler.NewPaymentsHandler(cfg)

	r.Get("/health", healthHandler)

	r.Get("/login", authHandler.Login)
	r.Get("/callback", authHandler.Callback)
	r.Get("/logout", authHandler.Logout)

	r.Route("/api", func(r chi.Router) {
		r.Get("/health", apiHealthHandler)

		r.With(auth.OptionalAuth).Get("/me", authHandler.Me)
		r.With(auth.OptionalAuth).Get("/modules", filterHandler.GetModules)
		r.With(auth.OptionalAuth).Get("/recent-activity", userHandler.GetRecentActivity)

		r.Group(func(r chi.Router) {
			r.Use(auth.RequireAuth)

			r.Post("/question", questionHandler.GetQuestion)
			r.Post("/check-answer", questionHandler.CheckAnswer)
			r.Post("/filters", filterHandler.GetFilters)

			r.Get("/stats", userHandler.GetStats)
			r.Get("/stats/{userID}", userHandler.GetUserStats)
			r.Get("/leaderboard", userHandler.GetLeaderboard)

			r.Post("/submit-flashcard", submissionHandler.SubmitFlashcard)
			r.Post("/submit-distractor", submissionHandler.SubmitDistractor)
			r.Post("/report-question", submissionHandler.ReportQuestion)
			r.Post("/check-duplicates", submissionHandler.CheckDuplicates)
			r.Post("/request-pdf-access", submissionHandler.RequestPDFAccess)

			r.Post("/suggest/topics", submissionHandler.SuggestTopics)
			r.Post("/suggest/subtopics", submissionHandler.SuggestSubtopics)
			r.Post("/suggest/tags", submissionHandler.SuggestTags)

			r.Get("/pdfs/list", pdfHandler.ListPDFs)
			r.Get("/pdfs/question/{questionID}", pdfHandler.GetPDFsForQuestion)
			r.Get("/pdf/{pdfID}", pdfHandler.ServePDF)

			r.Post("/pdfs/submit", pdfHandler.UploadPDF)
			r.Post("/pdfs/batch-submit", pdfHandler.BatchUploadPDF)
		})

		r.Group(func(r chi.Router) {
			r.Use(auth.RequireAdmin)

			r.Get("/admin/submissions", adminHandler.GetSubmissions)
			r.Post("/admin/approve-flashcard", adminHandler.ApproveFlashcard)
			r.Post("/admin/reject-flashcard", adminHandler.RejectFlashcard)
			r.Post("/admin/approve-distractor", adminHandler.ApproveDistractor)
			r.Post("/admin/reject-distractor", adminHandler.RejectDistractor)
			r.Post("/admin/discard-report", adminHandler.DiscardReport)
			r.Post("/admin/resolve-report", adminHandler.ResolveReport)
			r.Get("/admin/question/{questionID}", adminHandler.GetQuestionForReport)
			r.Post("/admin/approve-pdf-access", adminHandler.ApprovePDFAccess)
			r.Post("/admin/deny-pdf-access", adminHandler.DenyPDFAccess)
			r.Post("/admin/edit-answer", adminHandler.EditAnswer)

			r.Get("/admin/pdfs/list", pdfHandler.ListPDFs)
			r.Get("/admin/pdfs/{pdfID}", pdfHandler.GetPDFInfo)
			r.Post("/admin/pdfs/upload", pdfHandler.UploadPDF)
			r.Post("/admin/pdfs/batch-upload", pdfHandler.BatchUploadPDF)
			r.Put("/admin/pdfs/{pdfID}", pdfHandler.UpdatePDF)
			r.Delete("/admin/pdfs/{pdfID}", pdfHandler.DeletePDF)
			r.Delete("/admin/pdfs/{pdfID}/hard-delete", pdfHandler.HardDeletePDF)
			r.Post("/admin/pdfs/{pdfID}/restore", pdfHandler.RestorePDF)

			r.Get("/admin/pdfs/submitted", pdfHandler.ListSubmittedPDFs)
			r.Get("/admin/pdf/submitted/{pdfID}", pdfHandler.ServeSubmittedPDF)
			r.Post("/admin/pdfs/approve", pdfHandler.ApprovePDF)
			r.Post("/admin/pdfs/reject", pdfHandler.RejectPDF)
		})

		r.Group(func(r chi.Router) {
			r.Use(ingestHandler.APITokenAuth)

			r.Post("/ingest_flashcards", ingestHandler.IngestFlashcards)
			r.Post("/submit_distractors", ingestHandler.SubmitDistractors)
			r.Post("/check_duplicates", ingestHandler.CheckDuplicates)
			r.Post("/approve_flashcard", ingestHandler.ApproveFlashcard)
			r.Post("/reject_flashcard", ingestHandler.RejectFlashcard)
			r.Post("/approve_distractor", ingestHandler.ApproveDistractor)
			r.Post("/reject_distractor", ingestHandler.RejectDistractor)

			r.Post("/pdfs/upload", pdfHandler.UploadPDF)
			r.Post("/pdfs/batch-upload", pdfHandler.BatchUploadPDF)
		})

		r.Post("/github-sponsor", paymentsHandler.GitHubSponsor)
		r.Post("/github-star", paymentsHandler.GitHubStar)
	})

	r.Get("/ws", func(w http.ResponseWriter, r *http.Request) {
		realtime.ServeWs(wsHub, w, r)
	})

	staticFS := http.Dir("./web/dist")
	fileServer := http.FileServer(staticFS)
	r.Get("/*", func(w http.ResponseWriter, r *http.Request) {
		if _, err := staticFS.Open(r.URL.Path); err != nil {
			http.ServeFile(w, r, "./web/dist/index.html")
			return
		}
		fileServer.ServeHTTP(w, r)
	})

	return r
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

func apiHealthHandler(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	w.Header().Set("Content-Type", "application/json")

	dbStatus := "ok"
	statusCode := http.StatusOK

	if err := db.HealthCheck(ctx); err != nil {
		dbStatus = "unavailable"
		statusCode = http.StatusServiceUnavailable
	}

	w.WriteHeader(statusCode)
	json.NewEncoder(w).Encode(map[string]string{
		"status": "ok",
		"db":     dbStatus,
	})
}

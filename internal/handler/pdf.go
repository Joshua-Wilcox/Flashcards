package handler

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	"flashcards-go/internal/auth"
	"flashcards-go/internal/config"
	"flashcards-go/internal/db/queries"
	"flashcards-go/internal/services"

	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog/log"
)

type PDFHandler struct {
	cfg     *config.Config
	storage *services.PDFStorageService
}

func NewPDFHandler(cfg *config.Config) *PDFHandler {
	return &PDFHandler{
		cfg:     cfg,
		storage: services.NewPDFStorageService(cfg),
	}
}

func (h *PDFHandler) GetPDFsForQuestion(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	questionID := chi.URLParam(r, "questionID")

	maxPDFs := 3
	if m := r.URL.Query().Get("max_pdfs"); m != "" {
		if n, err := strconv.Atoi(m); err == nil && n > 0 && n <= 10 {
			maxPDFs = n
		}
	}

	pdfs, err := queries.GetPDFsForQuestion(ctx, questionID, maxPDFs)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get PDFs")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to get PDFs"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":     true,
		"question_id": questionID,
		"pdfs":        pdfs,
	})
}

func (h *PDFHandler) ServePDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)
	isAdmin := auth.GetIsAdmin(ctx)

	userIDInt, _ := strconv.ParseInt(userID, 10, 64)
	if !isAdmin && !auth.IsUserWhitelisted(userIDInt) {
		writeJSON(w, http.StatusForbidden, map[string]interface{}{
			"error":         "no_access",
			"message":       "You do not have permission to view PDFs. Please request access.",
			"needs_request": true,
		})
		return
	}

	pdfIDStr := chi.URLParam(r, "pdfID")
	pdfID, err := strconv.Atoi(pdfIDStr)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid PDF ID"})
		return
	}

	pdf, err := queries.GetPDFByID(ctx, pdfID)
	if err != nil || pdf == nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "PDF not found"})
		return
	}

	if !pdf.IsActive {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "PDF is no longer available"})
		return
	}

	h.servePDFData(w, r, pdf.StoragePath, pdf.OriginalFilename, pdf.MimeType)
}

// ServeSubmittedPDF serves a submitted (pending) PDF — admin only
func (h *PDFHandler) ServeSubmittedPDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	pdfIDStr := chi.URLParam(r, "pdfID")
	pdfID, err := strconv.Atoi(pdfIDStr)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid PDF ID"})
		return
	}

	pdf, err := queries.GetSubmittedPDFByID(ctx, pdfID)
	if err != nil || pdf == nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "Submitted PDF not found"})
		return
	}

	h.servePDFData(w, r, pdf.StoragePath, pdf.OriginalFilename, pdf.MimeType)
}

func (h *PDFHandler) servePDFData(w http.ResponseWriter, r *http.Request, storagePath, filename, mimeType string) {
	ctx := r.Context()
	data, contentType, err := h.storage.FetchFromStorage(ctx, storagePath)
	if err != nil {
		log.Error().Err(err).Str("path", storagePath).Msg("Failed to fetch PDF from storage")
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "PDF not found in storage"})
		return
	}

	if contentType == "" {
		contentType = mimeType
	}
	if contentType == "" {
		contentType = "application/pdf"
	}

	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Content-Disposition", `inline; filename="`+filename+`"`)
	w.Header().Set("Content-Length", strconv.Itoa(len(data)))
	w.WriteHeader(http.StatusOK)
	w.Write(data)
}

type UploadPDFRequest struct {
	ModuleID      int      `json:"module_id"`
	ModuleName    string   `json:"module_name"`
	TopicNames    []string `json:"topic_names"`
	SubtopicNames []string `json:"subtopic_names"`
	TagNames      []string `json:"tag_names"`
}


func (h *PDFHandler) UploadPDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)
	if userID == "" {
		userID = "api-upload"
	}

	if err := r.ParseMultipartForm(60 << 20); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Failed to parse form: " + err.Error()})
		return
	}

	file, header, err := r.FormFile("file")
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "No file provided"})
		return
	}
	defer file.Close()

	fileData, err := io.ReadAll(file)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to read file"})
		return
	}

	if err := services.ValidatePDF(fileData, header.Filename); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	moduleID := 0
	if m := r.FormValue("module_id"); m != "" {
		moduleID, _ = strconv.Atoi(m)
	}
	if moduleID == 0 {
		if moduleName := r.FormValue("module_name"); moduleName != "" {
			id, err := queries.GetModuleIDByName(ctx, moduleName)
			if err != nil || id == 0 {
				writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Module not found: " + moduleName})
				return
			}
			moduleID = id
		}
	}
	if moduleID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "module_id or module_name is required"})
		return
	}

	topicIDs := resolveIDsFromForm(ctx, r.Form["topic_names"], queries.GetOrCreateTopic)
	subtopicIDs := resolveIDsFromForm(ctx, r.Form["subtopic_names"], queries.GetOrCreateSubtopic)
	tagIDs := resolveIDsFromForm(ctx, r.Form["tag_names"], queries.GetOrCreateTag)

	storagePath, err := h.storage.UploadToStorage(ctx, fileData, header.Filename)
	if err != nil {
		log.Error().Err(err).Msg("Failed to upload PDF to storage")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to upload file"})
		return
	}

	pdfInsert := queries.PDFInsert{
		StoragePath:      storagePath,
		OriginalFilename: header.Filename,
		FileSize:         int64(len(fileData)),
		MimeType:         "application/pdf",
		ModuleID:         moduleID,
		UploadedBy:       userID,
	}

	// Everyone goes through the pending approval queue
	submittedID, err := queries.InsertSubmittedPDF(ctx, pdfInsert, topicIDs, subtopicIDs, tagIDs)
	if err != nil {
		log.Error().Err(err).Msg("Failed to insert submitted PDF")
		h.storage.DeleteFromStorage(ctx, storagePath)
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to submit PDF"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":      true,
		"pending":      true,
		"submitted_id": submittedID,
		"message":      "PDF submitted for review.",
	})
}

func (h *PDFHandler) BatchUploadPDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	userID := auth.GetUserID(ctx)
	if userID == "" {
		userID = "api-upload"
	}

	if err := r.ParseMultipartForm(200 << 20); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Failed to parse form: " + err.Error()})
		return
	}

	moduleID := 0
	if m := r.FormValue("module_id"); m != "" {
		moduleID, _ = strconv.Atoi(m)
	}
	if moduleID == 0 {
		if moduleName := r.FormValue("module_name"); moduleName != "" {
			id, err := queries.GetModuleIDByName(ctx, moduleName)
			if err != nil || id == 0 {
				writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Module not found: " + moduleName})
				return
			}
			moduleID = id
		}
	}
	if moduleID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "module_id or module_name is required"})
		return
	}

	topicIDs := resolveIDsFromForm(ctx, r.Form["topic_names"], queries.GetOrCreateTopic)
	subtopicIDs := resolveIDsFromForm(ctx, r.Form["subtopic_names"], queries.GetOrCreateSubtopic)
	tagIDs := resolveIDsFromForm(ctx, r.Form["tag_names"], queries.GetOrCreateTag)

	files := r.MultipartForm.File["files"]
	if len(files) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "No files provided"})
		return
	}

	var pendingIDs []int
	var errors []string

	for _, fileHeader := range files {
		file, err := fileHeader.Open()
		if err != nil {
			errors = append(errors, fileHeader.Filename+": failed to open")
			continue
		}

		fileData, err := io.ReadAll(file)
		file.Close()
		if err != nil {
			errors = append(errors, fileHeader.Filename+": failed to read")
			continue
		}

		if err := services.ValidatePDF(fileData, fileHeader.Filename); err != nil {
			errors = append(errors, fileHeader.Filename+": "+err.Error())
			continue
		}

		storagePath, err := h.storage.UploadToStorage(ctx, fileData, fileHeader.Filename)
		if err != nil {
			errors = append(errors, fileHeader.Filename+": upload failed")
			continue
		}

		pdfInsert := queries.PDFInsert{
			StoragePath:      storagePath,
			OriginalFilename: fileHeader.Filename,
			FileSize:         int64(len(fileData)),
			MimeType:         "application/pdf",
			ModuleID:         moduleID,
			UploadedBy:       userID,
		}

		// Everyone goes through the pending approval queue
		submittedID, err := queries.InsertSubmittedPDF(ctx, pdfInsert, topicIDs, subtopicIDs, tagIDs)
		if err != nil {
			h.storage.DeleteFromStorage(ctx, storagePath)
			errors = append(errors, fileHeader.Filename+": database insert failed")
			continue
		}
		pendingIDs = append(pendingIDs, submittedID)
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":     len(errors) == 0,
		"pending":     true,
		"pending_ids": pendingIDs,
		"errors":      errors,
		"message":     strconv.Itoa(len(pendingIDs)) + " of " + strconv.Itoa(len(files)) + " files submitted for review",
	})
}

func (h *PDFHandler) ListPDFs(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var moduleID *int
	if m := r.URL.Query().Get("module_id"); m != "" {
		if n, err := strconv.Atoi(m); err == nil {
			moduleID = &n
		}
	}

	isActive := true
	if a := r.URL.Query().Get("is_active"); a == "false" {
		isActive = false
	}

	limit := 50
	if l := r.URL.Query().Get("limit"); l != "" {
		if n, err := strconv.Atoi(l); err == nil && n > 0 && n <= 100 {
			limit = n
		}
	}

	offset := 0
	if o := r.URL.Query().Get("offset"); o != "" {
		if n, err := strconv.Atoi(o); err == nil && n >= 0 {
			offset = n
		}
	}

	params := queries.ListPDFsParams{
		ModuleID:     moduleID,
		IsActive:     isActive,
		TopicName:    r.URL.Query().Get("topic"),
		SubtopicName: r.URL.Query().Get("subtopic"),
		TagName:      r.URL.Query().Get("tag"),
		Limit:        limit,
		Offset:       offset,
	}

	pdfs, total, err := queries.ListPDFs(ctx, params)
	if err != nil {
		log.Error().Err(err).Msg("Failed to list PDFs")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to list PDFs"})
		return
	}
	if pdfs == nil {
		pdfs = []queries.PDF{}
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"pdfs":    pdfs,
		"total":   total,
		"limit":   limit,
		"offset":  offset,
	})
}

func (h *PDFHandler) GetPDFInfo(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	pdfIDStr := chi.URLParam(r, "pdfID")
	pdfID, err := strconv.Atoi(pdfIDStr)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid PDF ID"})
		return
	}

	pdf, err := queries.GetPDFWithMetadata(ctx, pdfID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get PDF")
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "PDF not found"})
		return
	}

	writeJSON(w, http.StatusOK, pdf)
}

type UpdatePDFRequest struct {
	ModuleID      int      `json:"module_id"`
	TopicIDs      []int    `json:"topic_ids"`
	SubtopicIDs   []int    `json:"subtopic_ids"`
	TagIDs        []int    `json:"tag_ids"`
	TopicNames    []string `json:"topic_names"`
	SubtopicNames []string `json:"subtopic_names"`
	TagNames      []string `json:"tag_names"`
}

func (h *PDFHandler) UpdatePDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	pdfIDStr := chi.URLParam(r, "pdfID")
	pdfID, err := strconv.Atoi(pdfIDStr)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid PDF ID"})
		return
	}

	var req UpdatePDFRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request body"})
		return
	}

	if req.ModuleID > 0 {
		if err := queries.UpdatePDFMetadata(ctx, pdfID, req.ModuleID); err != nil {
			log.Error().Err(err).Msg("Failed to update PDF module")
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to update PDF"})
			return
		}
	}

	if len(req.TopicIDs) > 0 {
		queries.SetPDFTopics(ctx, pdfID, req.TopicIDs)
	} else if len(req.TopicNames) > 0 {
		ids := resolveIDsFromForm(ctx, req.TopicNames, queries.GetOrCreateTopic)
		if len(ids) > 0 {
			queries.SetPDFTopics(ctx, pdfID, ids)
		}
	}

	if len(req.SubtopicIDs) > 0 {
		queries.SetPDFSubtopics(ctx, pdfID, req.SubtopicIDs)
	} else if len(req.SubtopicNames) > 0 {
		ids := resolveIDsFromForm(ctx, req.SubtopicNames, queries.GetOrCreateSubtopic)
		if len(ids) > 0 {
			queries.SetPDFSubtopics(ctx, pdfID, ids)
		}
	}

	if len(req.TagIDs) > 0 {
		queries.SetPDFTags(ctx, pdfID, req.TagIDs)
	} else if len(req.TagNames) > 0 {
		ids := resolveIDsFromForm(ctx, req.TagNames, queries.GetOrCreateTag)
		if len(ids) > 0 {
			queries.SetPDFTags(ctx, pdfID, ids)
		}
	}

	pdf, _ := queries.GetPDFByID(ctx, pdfID)

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"pdf":     pdf,
		"message": "PDF updated successfully",
	})
}

func (h *PDFHandler) DeletePDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	pdfIDStr := chi.URLParam(r, "pdfID")
	pdfID, err := strconv.Atoi(pdfIDStr)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid PDF ID"})
		return
	}

	if err := queries.SoftDeletePDF(ctx, pdfID); err != nil {
		log.Error().Err(err).Msg("Failed to delete PDF")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to delete PDF"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "PDF marked as inactive",
	})
}

func (h *PDFHandler) HardDeletePDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	pdfIDStr := chi.URLParam(r, "pdfID")
	pdfID, err := strconv.Atoi(pdfIDStr)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid PDF ID"})
		return
	}

	storagePath, err := queries.HardDeletePDF(ctx, pdfID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to hard delete PDF from database")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to delete PDF"})
		return
	}

	if storagePath != "" {
		if err := h.storage.DeleteFromStorage(ctx, storagePath); err != nil {
			log.Error().Err(err).Str("path", storagePath).Msg("Failed to delete PDF from storage")
		}
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "PDF permanently deleted",
	})
}

func (h *PDFHandler) RestorePDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	pdfIDStr := chi.URLParam(r, "pdfID")
	pdfID, err := strconv.Atoi(pdfIDStr)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid PDF ID"})
		return
	}

	if err := queries.RestorePDF(ctx, pdfID); err != nil {
		log.Error().Err(err).Msg("Failed to restore PDF")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to restore PDF"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "PDF restored",
	})
}

// ListSubmittedPDFs returns all PDFs awaiting admin approval
func (h *PDFHandler) ListSubmittedPDFs(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	pdfs, err := queries.ListSubmittedPDFs(ctx)
	if err != nil {
		log.Error().Err(err).Msg("Failed to list submitted PDFs")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to list submitted PDFs"})
		return
	}
	if pdfs == nil {
		pdfs = []queries.SubmittedPDF{}
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"pdfs":    pdfs,
	})
}

// ApprovePDF moves a submitted PDF to the live table
func (h *PDFHandler) ApprovePDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req struct {
		SubmittedID int `json:"submitted_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.SubmittedID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "submitted_id required"})
		return
	}

	newPDFID, err := queries.ApproveSubmittedPDF(ctx, req.SubmittedID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to approve submitted PDF")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to approve PDF"})
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"pdf_id":  newPDFID,
		"message": "PDF approved and published",
	})
}

// RejectPDF deletes a submitted PDF and cleans up storage
func (h *PDFHandler) RejectPDF(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req struct {
		SubmittedID int `json:"submitted_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.SubmittedID == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "submitted_id required"})
		return
	}

	storagePath, err := queries.RejectSubmittedPDF(ctx, req.SubmittedID)
	if err != nil {
		log.Error().Err(err).Msg("Failed to reject submitted PDF")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Failed to reject PDF"})
		return
	}

	if storagePath != "" {
		if err := h.storage.DeleteFromStorage(ctx, storagePath); err != nil {
			log.Error().Err(err).Str("path", storagePath).Msg("Failed to delete rejected PDF from storage")
		}
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"message": "PDF rejected and removed",
	})
}

// resolveIDsFromForm resolves a list of name strings to IDs using a get-or-create function.
// Handles both repeated form fields (["A", "B"]) and comma-separated values (["A,B"]).
func resolveIDsFromForm(ctx context.Context, names []string, getOrCreate func(context.Context, string) (int, error)) []int {
	var ids []int
	for _, raw := range names {
		for _, name := range strings.Split(raw, ",") {
			name = strings.TrimSpace(name)
			if name == "" {
				continue
			}
			id, err := getOrCreate(ctx, name)
			if err == nil {
				ids = append(ids, id)
			}
		}
	}
	return ids
}

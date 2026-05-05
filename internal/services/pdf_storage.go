package services

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"path/filepath"
	"strings"

	"flashcards-go/internal/config"

	"github.com/google/uuid"
	"github.com/rs/zerolog/log"
)

const (
	MaxPDFSize   = 50 * 1024 * 1024 // 50MB
	PDFBucket    = "pdfs"
	PDFMimeType  = "application/pdf"
)

type PDFStorageService struct {
	cfg *config.Config
}

func NewPDFStorageService(cfg *config.Config) *PDFStorageService {
	return &PDFStorageService{cfg: cfg}
}

// UploadToStorage uploads a file to Supabase Storage and returns the storage path
func (s *PDFStorageService) UploadToStorage(ctx context.Context, fileData []byte, filename string) (string, error) {
	// Generate unique storage path
	storagePath := fmt.Sprintf("%s/%s", uuid.New().String(), secureFilename(filename))

	url := fmt.Sprintf("%s/storage/v1/object/%s/%s", s.cfg.SupabaseURL, PDFBucket, storagePath)

	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(fileData))
	if err != nil {
		return "", fmt.Errorf("failed to create upload request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+s.cfg.SupabaseServiceRoleKey)
	req.Header.Set("Content-Type", PDFMimeType)
	req.Header.Set("x-upsert", "true")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("failed to upload to storage: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("storage upload failed with status %d: %s", resp.StatusCode, string(body))
	}

	log.Debug().Str("path", storagePath).Msg("PDF uploaded to storage")
	return storagePath, nil
}

// DeleteFromStorage deletes a file from Supabase Storage
func (s *PDFStorageService) DeleteFromStorage(ctx context.Context, storagePath string) error {
	if storagePath == "" {
		return nil
	}

	url := fmt.Sprintf("%s/storage/v1/object/%s/%s", s.cfg.SupabaseURL, PDFBucket, storagePath)

	req, err := http.NewRequestWithContext(ctx, "DELETE", url, nil)
	if err != nil {
		return fmt.Errorf("failed to create delete request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+s.cfg.SupabaseServiceRoleKey)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to delete from storage: %w", err)
	}
	defer resp.Body.Close()

	// 404 is acceptable - file may already be deleted
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNotFound {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("storage delete failed with status %d: %s", resp.StatusCode, string(body))
	}

	log.Debug().Str("path", storagePath).Msg("PDF deleted from storage")
	return nil
}

// GetSignedURL generates a temporary signed URL for accessing a PDF
func (s *PDFStorageService) GetSignedURL(ctx context.Context, storagePath string, expiresIn int) (string, error) {
	url := fmt.Sprintf("%s/storage/v1/object/sign/%s/%s", s.cfg.SupabaseURL, PDFBucket, storagePath)

	body := fmt.Sprintf(`{"expiresIn": %d}`, expiresIn)
	req, err := http.NewRequestWithContext(ctx, "POST", url, strings.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("failed to create sign request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+s.cfg.SupabaseServiceRoleKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("failed to get signed URL: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("sign URL failed with status %d: %s", resp.StatusCode, string(body))
	}

	return "", nil
}

// FetchFromStorage retrieves a file from Supabase Storage
func (s *PDFStorageService) FetchFromStorage(ctx context.Context, storagePath string) ([]byte, string, error) {
	url := fmt.Sprintf("%s/storage/v1/object/%s/%s", s.cfg.SupabaseURL, PDFBucket, storagePath)

	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, "", fmt.Errorf("failed to create fetch request: %w", err)
	}

	req.Header.Set("Authorization", "Bearer "+s.cfg.SupabaseServiceRoleKey)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, "", fmt.Errorf("failed to fetch from storage: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, "", fmt.Errorf("storage fetch failed with status %d: %s", resp.StatusCode, string(body))
	}

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, "", fmt.Errorf("failed to read response body: %w", err)
	}

	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = PDFMimeType
	}

	return data, contentType, nil
}

// ValidatePDF checks if the file is a valid PDF
func ValidatePDF(data []byte, filename string) error {
	if len(data) > MaxPDFSize {
		return fmt.Errorf("file size exceeds maximum of %d MB", MaxPDFSize/(1024*1024))
	}

	ext := strings.ToLower(filepath.Ext(filename))
	if ext != ".pdf" {
		return fmt.Errorf("only PDF files are allowed, got %s", ext)
	}

	// Check PDF magic bytes
	if len(data) < 4 || string(data[:4]) != "%PDF" {
		return fmt.Errorf("file does not appear to be a valid PDF")
	}

	return nil
}

// secureFilename sanitizes a filename for storage
func secureFilename(filename string) string {
	// Get base name without path
	filename = filepath.Base(filename)

	// Replace problematic characters
	replacer := strings.NewReplacer(
		" ", "_",
		"/", "_",
		"\\", "_",
		":", "_",
		"*", "_",
		"?", "_",
		"\"", "_",
		"<", "_",
		">", "_",
		"|", "_",
	)
	filename = replacer.Replace(filename)

	// Ensure it ends with .pdf
	if !strings.HasSuffix(strings.ToLower(filename), ".pdf") {
		filename += ".pdf"
	}

	return filename
}

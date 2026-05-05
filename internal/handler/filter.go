package handler

import (
	"encoding/json"
	"net/http"
	"sort"
	"strings"

	"flashcards-go/internal/db/queries"

	"github.com/rs/zerolog/log"
)

type FilterHandler struct{}

func NewFilterHandler() *FilterHandler {
	return &FilterHandler{}
}

type GetFiltersRequest struct {
	Module string   `json:"module"`
	Topics []string `json:"topics"`
}

type GetFiltersResponse struct {
	Topics    []string `json:"topics"`
	Subtopics []string `json:"subtopics"`
	Tags      []string `json:"tags"`
	Error     string   `json:"error,omitempty"`
}

func (h *FilterHandler) GetFilters(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	var req GetFiltersRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Invalid request data"})
		return
	}

	if req.Module == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "Module name required"})
		return
	}

	moduleID, err := queries.GetModuleIDByName(ctx, req.Module)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get module ID")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal server error"})
		return
	}
	if moduleID == 0 {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "Module not found"})
		return
	}

	topics, subtopics, tags, err := queries.GetModuleFilterData(ctx, moduleID, req.Topics)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get filter data")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal server error"})
		return
	}

	topicNames := make([]string, len(topics))
	for i, t := range topics {
		topicNames[i] = t.Name
	}

	subtopicNames := make([]string, len(subtopics))
	for i, s := range subtopics {
		subtopicNames[i] = s.Name
	}

	// Tags in the DB may be stored as comma-separated strings; split and deduplicate
	tagSet := make(map[string]struct{})
	for _, t := range tags {
		for _, part := range strings.Split(t.Name, ",") {
			part = strings.TrimSpace(part)
			if part != "" {
				tagSet[part] = struct{}{}
			}
		}
	}
	tagNames := make([]string, 0, len(tagSet))
	for name := range tagSet {
		tagNames = append(tagNames, name)
	}
	sort.Strings(tagNames)

	writeJSON(w, http.StatusOK, GetFiltersResponse{
		Topics:    topicNames,
		Subtopics: subtopicNames,
		Tags:      tagNames,
	})
}

func (h *FilterHandler) GetModules(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	modules, err := queries.GetAllModules(ctx)
	if err != nil {
		log.Error().Err(err).Msg("Failed to get modules")
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "Internal server error"})
		return
	}

	type ModuleGroup struct {
		Year    string           `json:"year"`
		Modules []queries.Module `json:"modules"`
	}

	groups := make(map[string][]queries.Module)
	for _, m := range modules {
		var key string
		if m.Year != nil {
			key = "Year " + string(rune('0'+*m.Year))
		} else {
			key = "Other"
		}
		groups[key] = append(groups[key], m)
	}

	var result []ModuleGroup
	for year, mods := range groups {
		result = append(result, ModuleGroup{Year: year, Modules: mods})
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"modules":       modules,
		"module_groups": result,
	})
}

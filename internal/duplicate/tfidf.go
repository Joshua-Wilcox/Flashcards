package duplicate

import (
	"math"
	"strings"
	"unicode"
)

var stopWords = map[string]bool{
	"the": true, "a": true, "an": true, "in": true, "on": true, "at": true,
	"to": true, "for": true, "with": true, "by": true, "about": true,
	"as": true, "of": true, "and": true, "or": true, "is": true, "are": true,
	"was": true, "were": true, "be": true, "been": true, "being": true,
	"have": true, "has": true, "had": true, "do": true, "does": true, "did": true,
	"what": true, "when": true, "where": true, "why": true, "how": true,
	"which": true, "who": true, "whom": true, "this": true, "that": true,
	"these": true, "those": true,
}

func tokenize(text string) []string {
	text = strings.ToLower(text)
	
	var result []string
	var current strings.Builder
	
	for _, r := range text {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			current.WriteRune(r)
		} else if current.Len() > 0 {
			word := current.String()
			if len(word) > 2 && !stopWords[word] {
				if len(word) > 6 {
					word = word[:6]
				}
				result = append(result, word)
			}
			current.Reset()
		}
	}
	
	if current.Len() > 0 {
		word := current.String()
		if len(word) > 2 && !stopWords[word] {
			if len(word) > 6 {
				word = word[:6]
			}
			result = append(result, word)
		}
	}
	
	return result
}

func termFrequency(tokens []string) map[string]float64 {
	tf := make(map[string]float64)
	for _, token := range tokens {
		tf[token]++
	}
	docLen := float64(len(tokens))
	if docLen == 0 {
		docLen = 1
	}
	for term := range tf {
		tf[term] /= docLen
	}
	return tf
}

func cosineSimilarity(vec1, vec2 map[string]float64) float64 {
	var dotProduct, mag1, mag2 float64
	
	for term, val1 := range vec1 {
		if val2, ok := vec2[term]; ok {
			dotProduct += val1 * val2
		}
		mag1 += val1 * val1
	}
	
	for _, val2 := range vec2 {
		mag2 += val2 * val2
	}
	
	mag1 = math.Sqrt(mag1)
	mag2 = math.Sqrt(mag2)
	
	if mag1 == 0 || mag2 == 0 {
		return 0
	}
	
	return dotProduct / (mag1 * mag2)
}

type Document struct {
	ID       string
	Question string
	Answer   string
}

type Match struct {
	ID         string  `json:"id"`
	Question   string  `json:"question"`
	Answer     string  `json:"answer"`
	Similarity float64 `json:"similarity"`
}

func FindSemanticDuplicates(queryText string, documents []Document, threshold float64, limit int) []Match {
	if len(documents) == 0 {
		return nil
	}
	
	allDocs := make([][]string, len(documents)+1)
	for i, doc := range documents {
		allDocs[i] = tokenize(doc.Question)
	}
	allDocs[len(documents)] = tokenize(queryText)
	
	termDocFreq := make(map[string]int)
	for _, tokens := range allDocs {
		seen := make(map[string]bool)
		for _, token := range tokens {
			if !seen[token] {
				termDocFreq[token]++
				seen[token] = true
			}
		}
	}
	
	numDocs := float64(len(allDocs))
	idf := make(map[string]float64)
	for term, freq := range termDocFreq {
		idf[term] = math.Log(numDocs / (1 + float64(freq)))
	}
	
	tfidfVectors := make([]map[string]float64, len(allDocs))
	for i, tokens := range allDocs {
		tf := termFrequency(tokens)
		tfidf := make(map[string]float64)
		for term, tfVal := range tf {
			tfidf[term] = tfVal * idf[term]
		}
		tfidfVectors[i] = tfidf
	}
	
	queryVector := tfidfVectors[len(documents)]
	
	type scoredDoc struct {
		index      int
		similarity float64
	}
	
	var scores []scoredDoc
	for i := 0; i < len(documents); i++ {
		sim := cosineSimilarity(queryVector, tfidfVectors[i])
		if sim >= threshold {
			scores = append(scores, scoredDoc{i, sim})
		}
	}
	
	for i := 0; i < len(scores)-1; i++ {
		for j := i + 1; j < len(scores); j++ {
			if scores[j].similarity > scores[i].similarity {
				scores[i], scores[j] = scores[j], scores[i]
			}
		}
	}
	
	if len(scores) > limit {
		scores = scores[:limit]
	}
	
	var matches []Match
	for _, s := range scores {
		doc := documents[s.index]
		matches = append(matches, Match{
			ID:         doc.ID,
			Question:   doc.Question,
			Answer:     doc.Answer,
			Similarity: s.similarity,
		})
	}
	
	return matches
}

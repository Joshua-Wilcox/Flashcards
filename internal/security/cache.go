package security

import (
	"sync"
	"time"
)

type CachedAnswer struct {
	QuestionID    string
	CorrectAnswer string
	ModuleID      int
	CreatedAt     time.Time
}

var (
	answerCache = make(map[string]*CachedAnswer)
	cacheMu     sync.RWMutex
)

func CacheAnswer(token string, questionID, correctAnswer string, moduleID int) {
	cacheMu.Lock()
	defer cacheMu.Unlock()
	
	answerCache[token] = &CachedAnswer{
		QuestionID:    questionID,
		CorrectAnswer: correctAnswer,
		ModuleID:      moduleID,
		CreatedAt:     time.Now(),
	}
}

func GetCachedAnswer(token string) *CachedAnswer {
	cacheMu.RLock()
	defer cacheMu.RUnlock()
	return answerCache[token]
}

func DeleteCachedAnswer(token string) {
	cacheMu.Lock()
	defer cacheMu.Unlock()
	delete(answerCache, token)
}

func CleanupExpiredCache(maxAge time.Duration) {
	cacheMu.Lock()
	defer cacheMu.Unlock()
	
	now := time.Now()
	for token, cached := range answerCache {
		if now.Sub(cached.CreatedAt) > maxAge {
			delete(answerCache, token)
		}
	}
}

func StartCacheCleanup(interval, maxAge time.Duration) {
	go func() {
		ticker := time.NewTicker(interval)
		for range ticker.C {
			CleanupExpiredCache(maxAge)
		}
	}()
}

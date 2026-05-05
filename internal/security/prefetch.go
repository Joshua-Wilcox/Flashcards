package security

import (
	"context"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
)

type PrefetchedQuestion struct {
	QuestionID    string
	Question      string
	Answer        string
	ModuleID      int
	Topics        []string
	Subtopics     []string
	Tags          []string
	Answers       []string
	AnswerIDs     []string
	AnswerTypes   []string
	AnswerMetadata []*int
	CreatedAt     time.Time
}

type UserQuestionQueue struct {
	Questions []*PrefetchedQuestion
	ModuleID  int
	Topics    []string
	Subtopics []string
	Tags      []string
	mu        sync.Mutex
}

var (
	userQueues   = make(map[string]*UserQuestionQueue)
	userQueuesMu sync.RWMutex
)

const (
	PrefetchQueueSize = 5
	PrefetchThreshold = 2
	MaxQueueAge       = 10 * time.Minute
)

func GetUserQueue(userID string) *UserQuestionQueue {
	userQueuesMu.RLock()
	queue := userQueues[userID]
	userQueuesMu.RUnlock()
	return queue
}

func GetOrCreateUserQueue(userID string, moduleID int, topics, subtopics, tags []string) *UserQuestionQueue {
	userQueuesMu.Lock()
	defer userQueuesMu.Unlock()

	queue, exists := userQueues[userID]
	if !exists || queue.ModuleID != moduleID || !slicesEqual(queue.Topics, topics) || !slicesEqual(queue.Subtopics, subtopics) || !slicesEqual(queue.Tags, tags) {
		queue = &UserQuestionQueue{
			Questions: make([]*PrefetchedQuestion, 0, PrefetchQueueSize),
			ModuleID:  moduleID,
			Topics:    topics,
			Subtopics: subtopics,
			Tags:      tags,
		}
		userQueues[userID] = queue
	}
	return queue
}

func (q *UserQuestionQueue) Pop() *PrefetchedQuestion {
	q.mu.Lock()
	defer q.mu.Unlock()

	if len(q.Questions) == 0 {
		return nil
	}

	now := time.Now()
	for len(q.Questions) > 0 && now.Sub(q.Questions[0].CreatedAt) > MaxQueueAge {
		q.Questions = q.Questions[1:]
	}

	if len(q.Questions) == 0 {
		return nil
	}

	question := q.Questions[0]
	q.Questions = q.Questions[1:]
	return question
}

func (q *UserQuestionQueue) Push(question *PrefetchedQuestion) {
	q.mu.Lock()
	defer q.mu.Unlock()

	if len(q.Questions) >= PrefetchQueueSize {
		return
	}

	question.CreatedAt = time.Now()
	q.Questions = append(q.Questions, question)
}

func (q *UserQuestionQueue) Len() int {
	q.mu.Lock()
	defer q.mu.Unlock()
	return len(q.Questions)
}

func (q *UserQuestionQueue) NeedsPrefetch() bool {
	return q.Len() < PrefetchThreshold
}

func (q *UserQuestionQueue) HasQuestionID(id string) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	for _, question := range q.Questions {
		if question.QuestionID == id {
			return true
		}
	}
	return false
}

func ClearUserQueue(userID string) {
	userQueuesMu.Lock()
	defer userQueuesMu.Unlock()
	delete(userQueues, userID)
}

func CleanupExpiredQueues() {
	userQueuesMu.Lock()
	defer userQueuesMu.Unlock()

	for userID, queue := range userQueues {
		queue.mu.Lock()
		if len(queue.Questions) == 0 {
			delete(userQueues, userID)
		} else {
			now := time.Now()
			allExpired := true
			for _, q := range queue.Questions {
				if now.Sub(q.CreatedAt) <= MaxQueueAge {
					allExpired = false
					break
				}
			}
			if allExpired {
				delete(userQueues, userID)
			}
		}
		queue.mu.Unlock()
	}
}

func StartQueueCleanup(interval time.Duration) {
	go func() {
		ticker := time.NewTicker(interval)
		for range ticker.C {
			CleanupExpiredQueues()
		}
	}()
}

type PrefetchFunc func(ctx context.Context, userID string, moduleID int, topics, subtopics, tags []string, excludeIDs []string) (*PrefetchedQuestion, error)

var prefetchFunc PrefetchFunc

func SetPrefetchFunc(fn PrefetchFunc) {
	prefetchFunc = fn
}

func TriggerPrefetch(userID string, moduleID int, topics, subtopics, tags []string) {
	if prefetchFunc == nil {
		return
	}

	go func() {
		queue := GetOrCreateUserQueue(userID, moduleID, topics, subtopics, tags)
		
		for queue.Len() < PrefetchQueueSize {
			queue.mu.Lock()
			excludeIDs := make([]string, len(queue.Questions))
			for i, q := range queue.Questions {
				excludeIDs[i] = q.QuestionID
			}
			queue.mu.Unlock()

			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			question, err := prefetchFunc(ctx, userID, moduleID, topics, subtopics, tags, excludeIDs)
			cancel()

			if err != nil {
				log.Debug().Err(err).Msg("Prefetch failed")
				break
			}
			if question == nil {
				break
			}

			queue.Push(question)
		}
	}()
}

func slicesEqual(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

package realtime

import (
	"encoding/json"
	"sync"
	"time"

	"github.com/rs/zerolog/log"
)

type ActivityEvent struct {
	UserID     string    `json:"user_id"`
	Username   string    `json:"username"`
	ModuleName string    `json:"module_name"`
	Streak     int       `json:"streak"`
	AnsweredAt time.Time `json:"answered_at"`
}

type LeaderboardUpdate struct {
	UserID         string `json:"user_id"`
	Username       string `json:"username"`
	ModuleID       int    `json:"module_id,omitempty"`
	CorrectAnswers int    `json:"correct_answers"`
	TotalAnswers   int    `json:"total_answers"`
	CurrentStreak  int    `json:"current_streak"`
	MaxStreak      int    `json:"max_streak"`
	ApprovedCards  int    `json:"approved_cards"`
	LastAnswerTime string `json:"last_answer_time"`
}

type Message struct {
	Type string      `json:"type"`
	Data interface{} `json:"data"`
}

type Hub struct {
	clients    map[*Client]bool
	broadcast  chan []byte
	register   chan *Client
	unregister chan *Client
	mu         sync.RWMutex
}

func NewHub() *Hub {
	return &Hub{
		clients:    make(map[*Client]bool),
		broadcast:  make(chan []byte, 256),
		register:   make(chan *Client),
		unregister: make(chan *Client),
	}
}

func (h *Hub) Run() {
	for {
		select {
		case client := <-h.register:
			h.mu.Lock()
			h.clients[client] = true
			h.mu.Unlock()
			log.Debug().Int("clients", len(h.clients)).Msg("Client connected")

		case client := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[client]; ok {
				delete(h.clients, client)
				close(client.send)
			}
			h.mu.Unlock()
			log.Debug().Int("clients", len(h.clients)).Msg("Client disconnected")

		case message := <-h.broadcast:
			h.mu.RLock()
			for client := range h.clients {
				select {
				case client.send <- message:
				default:
					close(client.send)
					delete(h.clients, client)
				}
			}
			h.mu.RUnlock()
		}
	}
}

func (h *Hub) Register(client *Client) {
	h.register <- client
}

func (h *Hub) Unregister(client *Client) {
	h.unregister <- client
}

func (h *Hub) BroadcastActivity(event ActivityEvent) {
	if event.AnsweredAt.IsZero() {
		event.AnsweredAt = time.Now()
	}

	msg := Message{
		Type: "activity",
		Data: event,
	}

	data, err := json.Marshal(msg)
	if err != nil {
		log.Error().Err(err).Msg("Failed to marshal activity event")
		return
	}

	select {
	case h.broadcast <- data:
	default:
		log.Warn().Msg("Broadcast channel full, dropping activity event")
	}
}

func (h *Hub) BroadcastLeaderboardUpdate(update LeaderboardUpdate) {
	msg := Message{
		Type: "leaderboard_update",
		Data: update,
	}

	data, err := json.Marshal(msg)
	if err != nil {
		log.Error().Err(err).Msg("Failed to marshal leaderboard update")
		return
	}

	select {
	case h.broadcast <- data:
	default:
		log.Warn().Msg("Broadcast channel full, dropping leaderboard update")
	}
}

func (h *Hub) ClientCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients)
}

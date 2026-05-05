package security

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"
	"time"
)

var tokenSecretKey string
var tokenExpirySeconds int64 = 600

func Init(secretKey string) {
	tokenSecretKey = secretKey
}

func SetTokenExpiry(seconds int) {
	tokenExpirySeconds = int64(seconds)
}

func GenerateSignedToken(questionID, userID string) string {
	timestamp := time.Now().Unix()
	payload := fmt.Sprintf("%s:%s:%d", questionID, userID, timestamp)
	
	h := hmac.New(sha256.New, []byte(tokenSecretKey))
	h.Write([]byte(payload))
	signature := fmt.Sprintf("%x", h.Sum(nil))
	
	token := base64.URLEncoding.EncodeToString([]byte(fmt.Sprintf("%s:%s", payload, signature)))
	return token
}

func VerifySignedToken(token, userID string) (questionID string, valid bool) {
	decoded, err := base64.URLEncoding.DecodeString(token)
	if err != nil {
		return "", false
	}
	
	parts := strings.Split(string(decoded), ":")
	if len(parts) != 4 {
		return "", false
	}
	
	tokenQuestionID := parts[0]
	tokenUserID := parts[1]
	timestampStr := parts[2]
	signature := parts[3]
	
	if tokenUserID != userID {
		return "", false
	}
	
	payload := fmt.Sprintf("%s:%s:%s", tokenQuestionID, tokenUserID, timestampStr)
	h := hmac.New(sha256.New, []byte(tokenSecretKey))
	h.Write([]byte(payload))
	expectedSig := fmt.Sprintf("%x", h.Sum(nil))
	
	if !hmac.Equal([]byte(signature), []byte(expectedSig)) {
		return "", false
	}
	
	timestamp, err := strconv.ParseInt(timestampStr, 10, 64)
	if err != nil {
		return "", false
	}

	if time.Now().Unix()-timestamp > tokenExpirySeconds {
		return "", false
	}

	return tokenQuestionID, true
}

func VerifyIngestToken(token, expectedToken string) bool {
	if expectedToken == "" || token == "" {
		return false
	}
	return hmac.Equal([]byte(strings.TrimSpace(token)), []byte(strings.TrimSpace(expectedToken)))
}

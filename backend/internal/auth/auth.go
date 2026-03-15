package auth

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

type contextKey string

const UserIDKey contextKey = "userId"
const IsInternalKey contextKey = "isInternal"

// Google's public certs endpoint for verifying ID tokens.
const googleCertsURL = "https://www.googleapis.com/oauth2/v3/tokeninfo"

type Auth struct {
	googleClientID string
	jwtSecret      []byte
}

func New(googleClientID, jwtSecret string) *Auth {
	return &Auth{
		googleClientID: googleClientID,
		jwtSecret:      []byte(jwtSecret),
	}
}

type GoogleClaims struct {
	Email string
	Name  string
}

func (a *Auth) ValidateGoogleToken(ctx context.Context, idToken string) (*GoogleClaims, error) {
	// Use Google's tokeninfo endpoint — lightweight, no GCP SDK/metadata dependency.
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, googleCertsURL+"?id_token="+idToken, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to validate token with Google: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("google token validation failed: %s", string(body))
	}

	var tokenInfo struct {
		Aud   string `json:"aud"`
		Email string `json:"email"`
		Name  string `json:"name"`
	}
	if err := json.Unmarshal(body, &tokenInfo); err != nil {
		return nil, fmt.Errorf("failed to parse token info: %w", err)
	}

	// Verify audience matches our client ID.
	if a.googleClientID != "" && tokenInfo.Aud != a.googleClientID {
		return nil, fmt.Errorf("token audience mismatch: got %s, want %s", tokenInfo.Aud, a.googleClientID)
	}

	if tokenInfo.Email == "" {
		return nil, fmt.Errorf("no email in google token")
	}

	return &GoogleClaims{Email: tokenInfo.Email, Name: tokenInfo.Name}, nil
}

func (a *Auth) GenerateJWT(userID string) (string, error) {
	claims := jwt.MapClaims{
		"sub": userID,
		"exp": time.Now().Add(30 * 24 * time.Hour).Unix(),
		"iat": time.Now().Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(a.jwtSecret)
}

func (a *Auth) ValidateJWT(tokenString string) (string, error) {
	token, err := jwt.Parse(tokenString, func(token *jwt.Token) (any, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return a.jwtSecret, nil
	})
	if err != nil {
		return "", err
	}

	claims, ok := token.Claims.(jwt.MapClaims)
	if !ok || !token.Valid {
		return "", fmt.Errorf("invalid token claims")
	}

	sub, _ := claims["sub"].(string)
	if sub == "" {
		return "", fmt.Errorf("missing sub claim")
	}
	return sub, nil
}

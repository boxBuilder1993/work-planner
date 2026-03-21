package model

import "encoding/json"

type Task struct {
	ID          string   `json:"id"`
	UserID      string   `json:"userId"`
	ParentID    *string  `json:"parentId"`
	Title       string   `json:"title"`
	Description string   `json:"description"`
	Status      string   `json:"status"`
	Priority    int      `json:"priority"`
	DueDate     *int64   `json:"dueDate"`
	TaskDate    *int64   `json:"taskDate"`
	PlannedTime *int64   `json:"plannedTime"`
	Duration    *float64 `json:"duration"`
	AiEnabled   bool            `json:"aiEnabled"`
	Level       *int            `json:"level"`
	Props       json.RawMessage `json:"props"`
	CreatedAt   int64           `json:"createdAt"`
	UpdatedAt   int64           `json:"updatedAt"`
}

type Comment struct {
	ID               string  `json:"id"`
	TaskID           string  `json:"taskId"`
	ParentCommentID  *string `json:"parentCommentId"`
	Text             string  `json:"text"`
	CommentType      string  `json:"commentType"`
	CreatedBy        string  `json:"createdBy"`
	ProposalStatus   *string `json:"proposalStatus"`
	ProposalFeedback *string `json:"proposalFeedback"`
	CreatedAt        int64   `json:"createdAt"`
	UpdatedAt        int64   `json:"updatedAt"`
}

type RepeatingTask struct {
	ID              string          `json:"id"`
	TaskID          string          `json:"taskId"`
	RepetitionType  string          `json:"repetitionType"`
	RepetitionProps json.RawMessage `json:"repetitionProps"`
	StartDate       int64           `json:"startDate"`
	LastCreatedAt   *int64          `json:"lastCreatedAt"`
	CreatedAt       int64           `json:"createdAt"`
	UpdatedAt       int64           `json:"updatedAt"`
}

type User struct {
	ID                 string  `json:"id"`
	Email              string  `json:"email"`
	Name               string  `json:"name"`
	GoogleRefreshToken *string `json:"-"`
	CreatedAt          int64   `json:"createdAt"`
}

// Request/response types

type AuthGoogleRequest struct {
	IDToken      string `json:"idToken"`
	RefreshToken string `json:"refreshToken,omitempty"`
}

type AuthResponse struct {
	Token string `json:"token"`
	User  User   `json:"user"`
}

type CreateTaskRequest struct {
	Title       string   `json:"title"`
	Description string   `json:"description,omitempty"`
	ParentID    *string  `json:"parentId,omitempty"`
	Priority    *int     `json:"priority,omitempty"`
	DueDate     *int64   `json:"dueDate,omitempty"`
	PlannedTime *int64   `json:"plannedTime,omitempty"`
	Duration    *float64 `json:"duration,omitempty"`
	AiEnabled   *bool            `json:"aiEnabled,omitempty"`
	Props       json.RawMessage `json:"props,omitempty"`
}

type UpdateTaskRequest struct {
	Title       *string  `json:"title,omitempty"`
	Description *string  `json:"description,omitempty"`
	Status      *string  `json:"status,omitempty"`
	Priority    *int     `json:"priority,omitempty"`
	DueDate     *int64   `json:"dueDate,omitempty"`
	PlannedTime *int64   `json:"plannedTime,omitempty"`
	Duration    *float64 `json:"duration,omitempty"`
	AiEnabled   *bool            `json:"aiEnabled,omitempty"`
	Props       json.RawMessage `json:"props,omitempty"`
}

type CreateCommentRequest struct {
	Text            string  `json:"text"`
	ParentCommentID *string `json:"parentCommentId,omitempty"`
	CommentType     string  `json:"commentType,omitempty"`
	CreatedBy       string  `json:"createdBy,omitempty"`
}

type UpdateProposalRequest struct {
	Status   string  `json:"status"`
	Feedback *string `json:"feedback,omitempty"`
}

type UpsertRepeatingTaskRequest struct {
	RepetitionType  string          `json:"repetitionType"`
	RepetitionProps json.RawMessage `json:"repetitionProps"`
	StartDate       int64           `json:"startDate"`
}

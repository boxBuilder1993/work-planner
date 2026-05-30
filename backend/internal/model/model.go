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
	ID               string          `json:"id"`
	TaskID           string          `json:"taskId"`
	ParentCommentID  *string         `json:"parentCommentId"`
	Text             string          `json:"text"`
	CommentType      string          `json:"commentType"`
	CreatedBy        string          `json:"createdBy"`
	ProposalStatus   *string         `json:"proposalStatus"`
	ProposalFeedback *string         `json:"proposalFeedback"`
	Props            json.RawMessage `json:"props"`
	CreatedAt        int64           `json:"createdAt"`
	UpdatedAt        int64           `json:"updatedAt"`
}

// WorkItem is the unit of AI execution. Every dispatch — whether triggered
// by a user mention, a manager orchestration mention, or a future periodic
// sweep — flows through a WorkItem row. See docs/WORK_ITEMS_DESIGN.md.
type WorkItem struct {
	ID                  string          `json:"id"`
	TaskID              string          `json:"taskId"`
	TriggeringCommentID *string         `json:"triggeringCommentId"`
	TargetPersona       string          `json:"targetPersona"`
	PromptContext       json.RawMessage `json:"promptContext"`
	Output              json.RawMessage `json:"output"`
	Status              string          `json:"status"`
	RetryCount          int             `json:"retryCount"`
	MaxRetries          int             `json:"maxRetries"`
	Attempts            json.RawMessage `json:"attempts"`
	LastError           *string         `json:"lastError"`
	CreatedAt           int64           `json:"createdAt"`
	UpdatedAt           int64           `json:"updatedAt"`
	DispatchedAt        *int64          `json:"dispatchedAt"`
	CompletedAt         *int64          `json:"completedAt"`
	Props               json.RawMessage `json:"props"`
}

// CreateWorkItemRequest is the body for POST /api/internal/work-items.
// triggering_comment_id is optional (sweep-created items have none).
type CreateWorkItemRequest struct {
	TaskID              string          `json:"taskId"`
	TriggeringCommentID *string         `json:"triggeringCommentId,omitempty"`
	TargetPersona       string          `json:"targetPersona"`
	PromptContext       json.RawMessage `json:"promptContext,omitempty"`
	MaxRetries          *int            `json:"maxRetries,omitempty"`
	Props               json.RawMessage `json:"props,omitempty"`
}

// UpdateWorkItemRequest is the body for PATCH /api/internal/work-items/:id.
// Only the listed fields can be patched; status transitions are validated
// server-side.
type UpdateWorkItemRequest struct {
	Status     *string         `json:"status,omitempty"`
	RetryCount *int            `json:"retryCount,omitempty"`
	Props      json.RawMessage `json:"props,omitempty"`
}

// SubmitWorkItemOutputRequest is the body for POST /work-items/:id/submit-output.
// Called by work_item_handler when the AI returns a parseable reply.
type SubmitWorkItemOutputRequest struct {
	Output json.RawMessage `json:"output"`
}

// RecordWorkItemAttemptRequest is the body for POST /work-items/:id/record-attempt.
// Called on dispatch failure. Appends to attempts[], increments retry_count,
// flips status to 'failed', sets last_error.
type RecordWorkItemAttemptRequest struct {
	Error      string  `json:"error"`
	DurationMs *int64  `json:"durationMs,omitempty"`
	CostUSD    *float64 `json:"costUsd,omitempty"`
	Runtime    string  `json:"runtime,omitempty"`
	Model      string  `json:"model,omitempty"`
	StopReason string  `json:"stopReason,omitempty"`
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

type AuthLocalRequest struct {
	Email string `json:"email"`
	Name  string `json:"name"`
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
	Text            string          `json:"text"`
	ParentCommentID *string         `json:"parentCommentId,omitempty"`
	CommentType     string          `json:"commentType,omitempty"`
	CreatedBy       string          `json:"createdBy,omitempty"`
	Props           json.RawMessage `json:"props,omitempty"`
}

type UpdateCommentRequest struct {
	Text  *string         `json:"text,omitempty"`
	Props json.RawMessage `json:"props,omitempty"`
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

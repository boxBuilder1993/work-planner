package store

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Store struct {
	pool *pgxpool.Pool
}

func New(pool *pgxpool.Pool) *Store {
	return &Store{pool: pool}
}

// ─── Users ──────────────────────────────────────────────────────────────────

func (s *Store) UpsertUser(ctx context.Context, u *model.User) error {
	_, err := s.pool.Exec(ctx, `
		INSERT INTO users (id, email, name, google_refresh_token, created_at)
		VALUES ($1, $2, $3, $4, $5)
		ON CONFLICT (email) DO UPDATE SET
			name = EXCLUDED.name,
			google_refresh_token = COALESCE(EXCLUDED.google_refresh_token, users.google_refresh_token)
	`, u.ID, u.Email, u.Name, u.GoogleRefreshToken, u.CreatedAt)
	return err
}

// GetSoleUserID returns the user id when exactly one user exists. Used by the
// internal CreateTask path to assign an owner to a root (parent-less) task in
// a single-user deployment, where there's no JWT to infer the owner from.
// Returns an error if zero or multiple users exist (caller should then require
// an explicit ownerId).
func (s *Store) GetSoleUserID(ctx context.Context) (string, error) {
	rows, err := s.pool.Query(ctx, `SELECT id FROM users LIMIT 2`)
	if err != nil {
		return "", err
	}
	defer rows.Close()
	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return "", err
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		return "", err
	}
	switch len(ids) {
	case 0:
		return "", fmt.Errorf("no users exist")
	case 1:
		return ids[0], nil
	default:
		return "", fmt.Errorf("multiple users exist; ownerId required")
	}
}

// UserExists reports whether a user row with the given id exists. Used to
// validate an explicit ownerId before assigning it (tasks.user_id is a FK).
func (s *Store) UserExists(ctx context.Context, userID string) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM users WHERE id = $1)`, userID).Scan(&exists)
	return exists, err
}

func (s *Store) GetUserByEmail(ctx context.Context, email string) (*model.User, error) {
	var u model.User
	err := s.pool.QueryRow(ctx, `
		SELECT id, email, name, google_refresh_token, created_at
		FROM users WHERE email = $1
	`, email).Scan(&u.ID, &u.Email, &u.Name, &u.GoogleRefreshToken, &u.CreatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &u, err
}

// ─── Tasks ──────────────────────────────────────────────────────────────────

func (s *Store) CreateTask(ctx context.Context, t *model.Task) error {
	_, err := s.pool.Exec(ctx, `
		INSERT INTO tasks (id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
	`, t.ID, t.UserID, t.ParentID, t.Title, t.Description, t.Status, t.Priority, t.DueDate, t.TaskDate, t.PlannedTime, t.Duration, t.AiEnabled, t.Level, t.Props, t.CreatedAt, t.UpdatedAt)
	return err
}

func (s *Store) GetTask(ctx context.Context, userID, taskID string) (*model.Task, error) {
	var t model.Task
	err := s.pool.QueryRow(ctx, `
		SELECT id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
		FROM tasks WHERE id = $1 AND user_id = $2
	`, taskID, userID).Scan(&t.ID, &t.UserID, &t.ParentID, &t.Title, &t.Description, &t.Status, &t.Priority, &t.DueDate, &t.TaskDate, &t.PlannedTime, &t.Duration, &t.AiEnabled, &t.Level, &t.Props, &t.CreatedAt, &t.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &t, err
}

func (s *Store) UpdateTask(ctx context.Context, userID, taskID string, req *model.UpdateTaskRequest, updatedAt int64) (*model.Task, error) {
	// Build dynamic SET clause.
	setClauses := []string{"updated_at = @updated_at"}
	args := pgx.NamedArgs{"id": taskID, "user_id": userID, "updated_at": updatedAt}

	if req.Title != nil {
		setClauses = append(setClauses, "title = @title")
		args["title"] = *req.Title
	}
	if req.Description != nil {
		setClauses = append(setClauses, "description = @description")
		args["description"] = *req.Description
	}
	if req.Status != nil {
		setClauses = append(setClauses, "status = @status")
		args["status"] = *req.Status
	}
	if req.Priority != nil {
		setClauses = append(setClauses, "priority = @priority")
		args["priority"] = *req.Priority
	}
	if req.DueDate != nil {
		setClauses = append(setClauses, "due_date = @due_date")
		args["due_date"] = *req.DueDate
	}
	if req.PlannedTime != nil {
		setClauses = append(setClauses, "planned_time = @planned_time")
		args["planned_time"] = *req.PlannedTime
	}
	if req.Duration != nil {
		setClauses = append(setClauses, "duration = @duration")
		args["duration"] = *req.Duration
	}
	if req.AiEnabled != nil {
		setClauses = append(setClauses, "ai_enabled = @ai_enabled")
		args["ai_enabled"] = *req.AiEnabled
	}
	if req.Props != nil {
		setClauses = append(setClauses, "props = props || @props")
		args["props"] = req.Props
	}

	query := fmt.Sprintf(`
		UPDATE tasks SET %s
		WHERE id = @id AND user_id = @user_id
		RETURNING id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
	`, joinStrings(setClauses, ", "))

	var t model.Task
	err := s.pool.QueryRow(ctx, query, args).Scan(
		&t.ID, &t.UserID, &t.ParentID, &t.Title, &t.Description, &t.Status, &t.Priority,
		&t.DueDate, &t.TaskDate, &t.PlannedTime, &t.Duration, &t.AiEnabled, &t.Level, &t.Props, &t.CreatedAt, &t.UpdatedAt,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &t, err
}

func (s *Store) DeleteTask(ctx context.Context, userID, taskID string) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM tasks WHERE id = $1 AND user_id = $2`, taskID, userID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

func (s *Store) ListRootTasks(ctx context.Context, userID string, status *string) ([]model.Task, error) {
	query := `SELECT id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
		FROM tasks WHERE user_id = $1 AND parent_id IS NULL`
	args := []any{userID}

	if status != nil {
		query += " AND status = $2"
		args = append(args, *status)
	}
	query += " ORDER BY created_at"

	return s.scanTasks(ctx, query, args...)
}

func (s *Store) ListChildren(ctx context.Context, userID, parentID string) ([]model.Task, error) {
	return s.scanTasks(ctx, `
		SELECT id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
		FROM tasks WHERE user_id = $1 AND parent_id = $2 ORDER BY created_at
	`, userID, parentID)
}

func (s *Store) GetBreadcrumbs(ctx context.Context, userID, taskID string) ([]model.Task, error) {
	return s.scanTasks(ctx, `
		WITH RECURSIVE chain AS (
			SELECT id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
			FROM tasks WHERE id = $1 AND user_id = $2
			UNION ALL
			SELECT t.id, t.user_id, t.parent_id, t.title, t.description, t.status, t.priority, t.due_date, t.task_date, t.planned_time, t.duration, t.ai_enabled, t.level, t.created_at, t.updated_at
			FROM tasks t JOIN chain c ON t.id = c.parent_id
		)
		SELECT * FROM chain ORDER BY created_at
	`, taskID, userID)
}

func (s *Store) ListExecutableTasks(ctx context.Context, userID string) ([]model.Task, error) {
	return s.scanTasks(ctx, `
		SELECT t.id, t.user_id, t.parent_id, t.title, t.description, t.status, t.priority, t.due_date, t.task_date, t.planned_time, t.duration, t.ai_enabled, t.level, t.created_at, t.updated_at
		FROM tasks t
		WHERE t.user_id = $1 AND t.status = 'PENDING'
			AND NOT EXISTS (SELECT 1 FROM tasks c WHERE c.parent_id = t.id)
		ORDER BY t.created_at
	`, userID)
}

func (s *Store) SearchTasks(ctx context.Context, userID, query string) ([]model.Task, error) {
	return s.scanTasks(ctx, `
		SELECT id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
		FROM tasks
		WHERE user_id = $1 AND (title ILIKE '%' || $2 || '%' OR description ILIKE '%' || $2 || '%')
		ORDER BY similarity(title, $2) DESC, created_at
		LIMIT 50
	`, userID, query)
}

func (s *Store) scanTasks(ctx context.Context, query string, args ...any) ([]model.Task, error) {
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tasks []model.Task
	for rows.Next() {
		var t model.Task
		if err := rows.Scan(&t.ID, &t.UserID, &t.ParentID, &t.Title, &t.Description, &t.Status, &t.Priority, &t.DueDate, &t.TaskDate, &t.PlannedTime, &t.Duration, &t.AiEnabled, &t.Level, &t.Props, &t.CreatedAt, &t.UpdatedAt); err != nil {
			return nil, err
		}
		tasks = append(tasks, t)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return tasks, nil
}

// ─── Comments ───────────────────────────────────────────────────────────────

func (s *Store) ListComments(ctx context.Context, userID, taskID string, commentType *string) ([]model.Comment, error) {
	query := `
		SELECT c.id, c.task_id, c.parent_comment_id, c.text, c.comment_type, c.created_by, c.proposal_status, c.proposal_feedback, c.props, c.created_at, c.updated_at
		FROM comments c JOIN tasks t ON c.task_id = t.id
		WHERE c.task_id = $1 AND t.user_id = $2`
	args := []any{taskID, userID}

	if commentType != nil {
		query += " AND c.comment_type = $3"
		args = append(args, *commentType)
	}
	query += " ORDER BY c.created_at ASC"

	return s.scanComments(ctx, query, args...)
}

func (s *Store) GetComment(ctx context.Context, userID, commentID string) (*model.Comment, error) {
	var c model.Comment
	err := s.pool.QueryRow(ctx, `
		SELECT c.id, c.task_id, c.parent_comment_id, c.text, c.comment_type, c.created_by, c.proposal_status, c.proposal_feedback, c.props, c.created_at, c.updated_at
		FROM comments c JOIN tasks t ON c.task_id = t.id
		WHERE c.id = $1 AND t.user_id = $2
	`, commentID, userID).Scan(&c.ID, &c.TaskID, &c.ParentCommentID, &c.Text, &c.CommentType, &c.CreatedBy, &c.ProposalStatus, &c.ProposalFeedback, &c.Props, &c.CreatedAt, &c.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &c, err
}

func (s *Store) CreateComment(ctx context.Context, userID string, c *model.Comment) error {
	// Verify task belongs to user.
	var exists bool
	err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM tasks WHERE id = $1 AND user_id = $2)`, c.TaskID, userID).Scan(&exists)
	if err != nil {
		return err
	}
	if !exists {
		return pgx.ErrNoRows
	}

	props := c.Props
	if len(props) == 0 {
		props = json.RawMessage("{}")
	}
	_, err = s.pool.Exec(ctx, `
		INSERT INTO comments (id, task_id, parent_comment_id, text, comment_type, created_by, proposal_status, proposal_feedback, props, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
	`, c.ID, c.TaskID, c.ParentCommentID, c.Text, c.CommentType, c.CreatedBy, c.ProposalStatus, c.ProposalFeedback, props, c.CreatedAt, c.UpdatedAt)
	return err
}

// UpdateComment performs a partial update on a comment. Currently supports text
// edits and partial-merge updates to props (top-level keys replace, arrays are
// replaced wholesale — same semantics as task props). Unscoped (no user check);
// intended for the internal API used by the ai-poller.
func (s *Store) UpdateComment(ctx context.Context, commentID string, req *model.UpdateCommentRequest, updatedAt int64) (*model.Comment, error) {
	setClauses := []string{"updated_at = @updated_at"}
	args := pgx.NamedArgs{
		"id":         commentID,
		"updated_at": updatedAt,
	}

	if req.Text != nil {
		setClauses = append(setClauses, "text = @text")
		args["text"] = *req.Text
	}
	if req.Props != nil {
		// Explicit ::jsonb cast — pgx v5 infers json.RawMessage as bytea
		// without a hint, and `jsonb || bytea` is not a valid operator.
		setClauses = append(setClauses, "props = props || @props::jsonb")
		args["props"] = string(req.Props)
	}

	query := fmt.Sprintf(`
		UPDATE comments SET %s
		WHERE id = @id
		RETURNING id, task_id, parent_comment_id, text, comment_type, created_by, proposal_status, proposal_feedback, props, created_at, updated_at
	`, joinStrings(setClauses, ", "))

	var c model.Comment
	err := s.pool.QueryRow(ctx, query, args).Scan(
		&c.ID, &c.TaskID, &c.ParentCommentID, &c.Text, &c.CommentType, &c.CreatedBy, &c.ProposalStatus, &c.ProposalFeedback, &c.Props, &c.CreatedAt, &c.UpdatedAt,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &c, err
}

// ListCommentsNeedingAIReply returns comments that:
//   - contain an @ai mention (loose ILIKE match; poller does final regex check)
//   - were NOT authored by an AI persona EXCEPT `ai-manager`. The manager
//     is the only persona allowed to dispatch other personas (orchestrator
//     role); all other AI replies are dispatch dead-ends. The poller adds a
//     second guard against manager→manager self-loops.
//   - have `ai-comment-status` of either NULL (never tried) or `failed`
//     (last cycle exhausted retries). The poller keeps retrying failed
//     mentions every cycle — manual intervention (edit the comment, flip
//     status) is the only stop signal.
//
// Replied / dispatched comments are excluded. The poller is the sole
// caller; no user scoping.
func (s *Store) ListCommentsNeedingAIReply(ctx context.Context) ([]model.Comment, error) {
	return s.scanComments(ctx, `
		SELECT c.id, c.task_id, c.parent_comment_id, c.text, c.comment_type, c.created_by, c.proposal_status, c.proposal_feedback, c.props, c.created_at, c.updated_at
		FROM comments c
		WHERE c.text ILIKE '%@ai%'
		  AND (c.created_by NOT LIKE 'ai-%' OR c.created_by = 'ai-manager')
		  AND (
		    (c.props->>'ai-comment-status') IS NULL
		    OR (c.props->>'ai-comment-status') = 'failed'
		  )
		ORDER BY c.created_at ASC
	`)
}

func (s *Store) UpdateProposalStatus(ctx context.Context, userID, commentID, status string, feedback *string, updatedAt int64) (*model.Comment, error) {
	var c model.Comment
	err := s.pool.QueryRow(ctx, `
		UPDATE comments SET proposal_status = $1, proposal_feedback = $2, updated_at = $3
		WHERE id = $4 AND comment_type = 'PROPOSAL'
		AND task_id IN (SELECT id FROM tasks WHERE user_id = $5)
		RETURNING id, task_id, parent_comment_id, text, comment_type, created_by, proposal_status, proposal_feedback, props, created_at, updated_at
	`, status, feedback, updatedAt, commentID, userID).Scan(
		&c.ID, &c.TaskID, &c.ParentCommentID, &c.Text, &c.CommentType, &c.CreatedBy, &c.ProposalStatus, &c.ProposalFeedback, &c.Props, &c.CreatedAt, &c.UpdatedAt,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &c, err
}

func (s *Store) UpdateProposalStatusUnscoped(ctx context.Context, commentID, status string, feedback *string, updatedAt int64) (*model.Comment, error) {
	var c model.Comment
	err := s.pool.QueryRow(ctx, `
		UPDATE comments SET proposal_status = $1, proposal_feedback = $2, updated_at = $3
		WHERE id = $4 AND comment_type = 'PROPOSAL'
		RETURNING id, task_id, parent_comment_id, text, comment_type, created_by, proposal_status, proposal_feedback, props, created_at, updated_at
	`, status, feedback, updatedAt, commentID).Scan(
		&c.ID, &c.TaskID, &c.ParentCommentID, &c.Text, &c.CommentType, &c.CreatedBy, &c.ProposalStatus, &c.ProposalFeedback, &c.Props, &c.CreatedAt, &c.UpdatedAt,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &c, err
}

func (s *Store) DeleteComment(ctx context.Context, userID, commentID string) error {
	// Verify comment's task belongs to user.
	tag, err := s.pool.Exec(ctx, `
		DELETE FROM comments WHERE id = $1
		AND task_id IN (SELECT id FROM tasks WHERE user_id = $2)
	`, commentID, userID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

func (s *Store) scanComments(ctx context.Context, query string, args ...any) ([]model.Comment, error) {
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var comments []model.Comment
	for rows.Next() {
		var c model.Comment
		if err := rows.Scan(&c.ID, &c.TaskID, &c.ParentCommentID, &c.Text, &c.CommentType, &c.CreatedBy, &c.ProposalStatus, &c.ProposalFeedback, &c.Props, &c.CreatedAt, &c.UpdatedAt); err != nil {
			return nil, err
		}
		comments = append(comments, c)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return comments, nil
}

// ─── Repeating Tasks ────────────────────────────────────────────────────────

func (s *Store) GetRepeatingTask(ctx context.Context, userID, taskID string) (*model.RepeatingTask, error) {
	var rt model.RepeatingTask
	err := s.pool.QueryRow(ctx, `
		SELECT r.id, r.task_id, r.repetition_type, r.repetition_props, r.start_date, r.last_created_at, r.created_at, r.updated_at
		FROM repeating_tasks r JOIN tasks t ON r.task_id = t.id
		WHERE r.task_id = $1 AND t.user_id = $2
	`, taskID, userID).Scan(&rt.ID, &rt.TaskID, &rt.RepetitionType, &rt.RepetitionProps, &rt.StartDate, &rt.LastCreatedAt, &rt.CreatedAt, &rt.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &rt, err
}

func (s *Store) UpsertRepeatingTask(ctx context.Context, userID string, rt *model.RepeatingTask) error {
	// Verify task belongs to user.
	var exists bool
	err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM tasks WHERE id = $1 AND user_id = $2)`, rt.TaskID, userID).Scan(&exists)
	if err != nil {
		return err
	}
	if !exists {
		return pgx.ErrNoRows
	}

	_, err = s.pool.Exec(ctx, `
		INSERT INTO repeating_tasks (id, task_id, repetition_type, repetition_props, start_date, last_created_at, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		ON CONFLICT (task_id) DO UPDATE SET
			repetition_type = EXCLUDED.repetition_type,
			repetition_props = EXCLUDED.repetition_props,
			start_date = EXCLUDED.start_date,
			updated_at = EXCLUDED.updated_at
	`, rt.ID, rt.TaskID, rt.RepetitionType, rt.RepetitionProps, rt.StartDate, rt.LastCreatedAt, rt.CreatedAt, rt.UpdatedAt)
	return err
}

func (s *Store) DeleteRepeatingTask(ctx context.Context, userID, taskID string) error {
	tag, err := s.pool.Exec(ctx, `
		DELETE FROM repeating_tasks WHERE task_id = $1
		AND task_id IN (SELECT id FROM tasks WHERE user_id = $2)
	`, taskID, userID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

// ─── Recurring Worker Queries ───────────────────────────────────────────────

type RepeatingTaskWithTemplate struct {
	Rule     model.RepeatingTask
	Template model.Task
}

func (s *Store) ListAllRepeatingTasksWithTemplates(ctx context.Context) ([]RepeatingTaskWithTemplate, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT
			r.id, r.task_id, r.repetition_type, r.repetition_props, r.start_date, r.last_created_at, r.created_at, r.updated_at,
			t.id, t.user_id, t.parent_id, t.title, t.description, t.status, t.priority, t.due_date, t.task_date, t.planned_time, t.duration, t.ai_enabled, t.level, t.created_at, t.updated_at
		FROM repeating_tasks r
		JOIN tasks t ON r.task_id = t.id
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []RepeatingTaskWithTemplate
	for rows.Next() {
		var item RepeatingTaskWithTemplate
		if err := rows.Scan(
			&item.Rule.ID, &item.Rule.TaskID, &item.Rule.RepetitionType, &item.Rule.RepetitionProps, &item.Rule.StartDate, &item.Rule.LastCreatedAt, &item.Rule.CreatedAt, &item.Rule.UpdatedAt,
			&item.Template.ID, &item.Template.UserID, &item.Template.ParentID, &item.Template.Title, &item.Template.Description, &item.Template.Status, &item.Template.Priority, &item.Template.DueDate, &item.Template.TaskDate, &item.Template.PlannedTime, &item.Template.Duration, &item.Template.AiEnabled, &item.Template.Level, &item.Template.Props, &item.Template.CreatedAt, &item.Template.UpdatedAt,
		); err != nil {
			return nil, err
		}
		results = append(results, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return results, nil
}

func (s *Store) UpdateRepeatingTaskLastCreated(ctx context.Context, ruleID string, lastCreatedAt int64) error {
	_, err := s.pool.Exec(ctx, `UPDATE repeating_tasks SET last_created_at = $1, updated_at = $1 WHERE id = $2`, lastCreatedAt, ruleID)
	return err
}

func (s *Store) IsTaskClosed(ctx context.Context, taskID string) (bool, error) {
	var status string
	err := s.pool.QueryRow(ctx, `SELECT status FROM tasks WHERE id = $1`, taskID).Scan(&status)
	if err == pgx.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return status == "CLOSED", nil
}

// ─── Internal (unscoped) queries ────────────────────────────────────────────

func (s *Store) ListAllRootTasks(ctx context.Context, status *string) ([]model.Task, error) {
	query := `SELECT id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
		FROM tasks WHERE parent_id IS NULL`
	var args []any

	if status != nil {
		query += " AND status = $1"
		args = append(args, *status)
	}
	query += " ORDER BY created_at"

	return s.scanTasks(ctx, query, args...)
}

func (s *Store) SearchAllTasks(ctx context.Context, status *string, aiStatus *string, algorithm *string, aiEnabled *bool) ([]model.Task, error) {
	query := `SELECT id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
		FROM tasks WHERE 1=1`
	var args []any
	argIdx := 1

	if status != nil {
		query += fmt.Sprintf(" AND status = $%d", argIdx)
		args = append(args, *status)
		argIdx++
	}
	if aiEnabled != nil {
		query += fmt.Sprintf(" AND ai_enabled = $%d", argIdx)
		args = append(args, *aiEnabled)
		argIdx++
	}
	if aiStatus != nil {
		query += fmt.Sprintf(" AND props->>'aiStatus' = $%d", argIdx)
		args = append(args, *aiStatus)
		argIdx++
	}
	if algorithm != nil {
		query += fmt.Sprintf(" AND props->>'algorithm' = $%d", argIdx)
		args = append(args, *algorithm)
		argIdx++
	}
	query += " ORDER BY created_at DESC"

	return s.scanTasks(ctx, query, args...)
}

func (s *Store) ListAllChildren(ctx context.Context, parentID string) ([]model.Task, error) {
	return s.scanTasks(ctx, `
		SELECT id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
		FROM tasks WHERE parent_id = $1 ORDER BY created_at
	`, parentID)
}

func (s *Store) ListAllComments(ctx context.Context, taskID string, commentType *string) ([]model.Comment, error) {
	query := `
		SELECT c.id, c.task_id, c.parent_comment_id, c.text, c.comment_type, c.created_by, c.proposal_status, c.proposal_feedback, c.props, c.created_at, c.updated_at
		FROM comments c
		WHERE c.task_id = $1`
	args := []any{taskID}

	if commentType != nil {
		query += " AND c.comment_type = $2"
		args = append(args, *commentType)
	}
	query += " ORDER BY c.created_at ASC"

	return s.scanComments(ctx, query, args...)
}

func (s *Store) GetTaskByID(ctx context.Context, taskID string) (*model.Task, error) {
	var t model.Task
	err := s.pool.QueryRow(ctx, `
		SELECT id, user_id, parent_id, title, description, status, priority, due_date, task_date, planned_time, duration, ai_enabled, level, props, created_at, updated_at
		FROM tasks WHERE id = $1
	`, taskID).Scan(&t.ID, &t.UserID, &t.ParentID, &t.Title, &t.Description, &t.Status, &t.Priority, &t.DueDate, &t.TaskDate, &t.PlannedTime, &t.Duration, &t.AiEnabled, &t.Level, &t.Props, &t.CreatedAt, &t.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &t, err
}

// ─── WorkItems ──────────────────────────────────────────────────────────────

// CreateWorkItemIdempotent inserts a new WorkItem, or — if a WorkItem already
// exists for the given triggering_comment_id — returns the existing one
// without modification. This is the load-bearing idempotency primitive that
// makes concurrent poll cycles safe (a unique partial index on
// triggering_comment_id provides DB-level fallback).
//
// triggering_comment_id may be nil for sweep-created WorkItems; in that case
// we always insert (no idempotency check possible).
func (s *Store) CreateWorkItemIdempotent(ctx context.Context, w *model.WorkItem) (*model.WorkItem, bool, error) {
	// If a triggering comment is given, check first within a serializable
	// transaction so concurrent inserts can't both succeed. The unique
	// partial index is the second line of defense.
	if w.TriggeringCommentID != nil {
		tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.Serializable})
		if err != nil {
			return nil, false, err
		}
		defer tx.Rollback(ctx) //nolint:errcheck

		var existing model.WorkItem
		err = tx.QueryRow(ctx, `
			SELECT id, task_id, triggering_comment_id, target_persona, prompt_context, output,
			       status, retry_count, max_retries, attempts, last_error,
			       created_at, updated_at, dispatched_at, completed_at, props
			FROM work_items
			WHERE triggering_comment_id = $1
		`, *w.TriggeringCommentID).Scan(
			&existing.ID, &existing.TaskID, &existing.TriggeringCommentID, &existing.TargetPersona,
			&existing.PromptContext, &existing.Output,
			&existing.Status, &existing.RetryCount, &existing.MaxRetries, &existing.Attempts, &existing.LastError,
			&existing.CreatedAt, &existing.UpdatedAt, &existing.DispatchedAt, &existing.CompletedAt, &existing.Props,
		)
		if err == nil {
			// Already exists — return existing, don't insert.
			if err := tx.Commit(ctx); err != nil {
				return nil, false, err
			}
			return &existing, false, nil
		}
		if err != pgx.ErrNoRows {
			return nil, false, err
		}

		if err := insertWorkItemTx(ctx, tx, w); err != nil {
			return nil, false, err
		}
		if err := tx.Commit(ctx); err != nil {
			return nil, false, err
		}
		return w, true, nil
	}

	// No triggering comment → straight insert, no idempotency check.
	if err := insertWorkItemPool(ctx, s.pool, w); err != nil {
		return nil, false, err
	}
	return w, true, nil
}

// Concrete typed inserts so callers can pass either the pool or a tx
// without a generic interface dance (pgconn.CommandTag isn't worth wrapping).
func insertWorkItemPool(ctx context.Context, pool *pgxpool.Pool, w *model.WorkItem) error {
	_, err := pool.Exec(ctx, insertWorkItemSQL,
		w.ID, w.TaskID, w.TriggeringCommentID, w.TargetPersona,
		w.PromptContext, w.Output, w.Status, w.RetryCount, w.MaxRetries,
		w.Attempts, w.LastError, w.CreatedAt, w.UpdatedAt, w.DispatchedAt, w.CompletedAt, w.Props,
	)
	return err
}

func insertWorkItemTx(ctx context.Context, tx pgx.Tx, w *model.WorkItem) error {
	_, err := tx.Exec(ctx, insertWorkItemSQL,
		w.ID, w.TaskID, w.TriggeringCommentID, w.TargetPersona,
		w.PromptContext, w.Output, w.Status, w.RetryCount, w.MaxRetries,
		w.Attempts, w.LastError, w.CreatedAt, w.UpdatedAt, w.DispatchedAt, w.CompletedAt, w.Props,
	)
	return err
}

const insertWorkItemSQL = `
	INSERT INTO work_items (
		id, task_id, triggering_comment_id, target_persona,
		prompt_context, output, status, retry_count, max_retries,
		attempts, last_error, created_at, updated_at, dispatched_at, completed_at, props
	) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
`

// GetWorkItem fetches a WorkItem by ID. Returns (nil, nil) on not-found.
func (s *Store) GetWorkItem(ctx context.Context, id string) (*model.WorkItem, error) {
	var w model.WorkItem
	err := s.pool.QueryRow(ctx, `
		SELECT id, task_id, triggering_comment_id, target_persona, prompt_context, output,
		       status, retry_count, max_retries, attempts, last_error,
		       created_at, updated_at, dispatched_at, completed_at, props
		FROM work_items WHERE id = $1
	`, id).Scan(
		&w.ID, &w.TaskID, &w.TriggeringCommentID, &w.TargetPersona, &w.PromptContext, &w.Output,
		&w.Status, &w.RetryCount, &w.MaxRetries, &w.Attempts, &w.LastError,
		&w.CreatedAt, &w.UpdatedAt, &w.DispatchedAt, &w.CompletedAt, &w.Props,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &w, err
}

// ListWorkItems supports filtering by task_id, status, target_persona.
func (s *Store) ListWorkItems(ctx context.Context, taskID, status, persona *string) ([]model.WorkItem, error) {
	query := `
		SELECT id, task_id, triggering_comment_id, target_persona, prompt_context, output,
		       status, retry_count, max_retries, attempts, last_error,
		       created_at, updated_at, dispatched_at, completed_at, props
		FROM work_items WHERE 1=1`
	args := []any{}
	if taskID != nil {
		args = append(args, *taskID)
		query += fmt.Sprintf(" AND task_id = $%d", len(args))
	}
	if status != nil {
		args = append(args, *status)
		query += fmt.Sprintf(" AND status = $%d", len(args))
	}
	if persona != nil {
		args = append(args, *persona)
		query += fmt.Sprintf(" AND target_persona = $%d", len(args))
	}
	query += " ORDER BY created_at"
	return s.scanWorkItems(ctx, query, args...)
}

// ListWorkItemsForPickup returns WorkItems eligible for dispatch by the
// work_item_handler poller. Eligibility:
//   - status = 'pending', OR
//   - status = 'failed' AND retry_count < max_retries (auto-retry)
//
// Ordered oldest-first so the poller naturally drains backlogged work.
func (s *Store) ListWorkItemsForPickup(ctx context.Context) ([]model.WorkItem, error) {
	return s.scanWorkItems(ctx, `
		SELECT id, task_id, triggering_comment_id, target_persona, prompt_context, output,
		       status, retry_count, max_retries, attempts, last_error,
		       created_at, updated_at, dispatched_at, completed_at, props
		FROM work_items
		WHERE status = 'pending'
		   OR (status = 'failed' AND retry_count < max_retries)
		ORDER BY created_at
	`)
}

// CountDispatchedForTask returns how many WorkItems are currently dispatched
// on a given task. Used by the poller's per-task concurrency cap.
func (s *Store) CountDispatchedForTask(ctx context.Context, taskID string) (int, error) {
	var count int
	err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM work_items WHERE task_id = $1 AND status = 'dispatched'`,
		taskID,
	).Scan(&count)
	return count, err
}

// validWorkItemTransitions lists allowed status transitions. The state
// machine is enforced server-side; PATCHes that violate it return 400.
var validWorkItemTransitions = map[string]map[string]bool{
	"pending":    {"dispatched": true, "cancelled": true},
	"dispatched": {"completed": true, "failed": true, "cancelled": true},
	"completed":  {}, // terminal
	"failed":     {"dispatched": true, "cancelled": true}, // retry path
	"cancelled":  {}, // terminal
}

// UpdateWorkItem applies a partial update. Supports status transitions (with
// validation), retry_count writes (for manual retry reset), and props merge.
// Returns (nil, nil) on not-found, (nil, err) on invalid transition (err
// message reports the bad transition).
func (s *Store) UpdateWorkItem(ctx context.Context, id string, req *model.UpdateWorkItemRequest, updatedAt int64) (*model.WorkItem, error) {
	// Read current state to validate transitions.
	current, err := s.GetWorkItem(ctx, id)
	if err != nil {
		return nil, err
	}
	if current == nil {
		return nil, nil
	}

	if req.Status != nil {
		allowed, ok := validWorkItemTransitions[current.Status]
		if !ok || !allowed[*req.Status] {
			return nil, fmt.Errorf("invalid status transition: %s → %s", current.Status, *req.Status)
		}
	}

	setClauses := []string{"updated_at = @updated_at"}
	args := pgx.NamedArgs{"id": id, "updated_at": updatedAt}

	if req.Status != nil {
		setClauses = append(setClauses, "status = @status")
		args["status"] = *req.Status
		// dispatched_at / completed_at side-effects of certain transitions:
		if *req.Status == "dispatched" {
			setClauses = append(setClauses, "dispatched_at = @updated_at")
		}
		if *req.Status == "completed" {
			setClauses = append(setClauses, "completed_at = @updated_at")
		}
	}
	if req.RetryCount != nil {
		setClauses = append(setClauses, "retry_count = @retry_count")
		args["retry_count"] = *req.RetryCount
	}
	if req.Props != nil {
		setClauses = append(setClauses, "props = props || @props")
		args["props"] = req.Props
	}

	query := fmt.Sprintf(`
		UPDATE work_items SET %s WHERE id = @id
		RETURNING id, task_id, triggering_comment_id, target_persona, prompt_context, output,
		          status, retry_count, max_retries, attempts, last_error,
		          created_at, updated_at, dispatched_at, completed_at, props
	`, joinStrings(setClauses, ", "))

	var w model.WorkItem
	err = s.pool.QueryRow(ctx, query, args).Scan(
		&w.ID, &w.TaskID, &w.TriggeringCommentID, &w.TargetPersona, &w.PromptContext, &w.Output,
		&w.Status, &w.RetryCount, &w.MaxRetries, &w.Attempts, &w.LastError,
		&w.CreatedAt, &w.UpdatedAt, &w.DispatchedAt, &w.CompletedAt, &w.Props,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &w, err
}

// SubmitWorkItemOutput records the AI's parsed output and flips status to
// 'completed'. Only valid when current status is 'dispatched' (the runtime
// for any other status would be inconsistent — caller responsibility).
func (s *Store) SubmitWorkItemOutput(ctx context.Context, id string, output json.RawMessage, completedAt int64) (*model.WorkItem, error) {
	var w model.WorkItem
	err := s.pool.QueryRow(ctx, `
		UPDATE work_items
		SET output = $2, status = 'completed', completed_at = $3, updated_at = $3
		WHERE id = $1 AND status = 'dispatched'
		RETURNING id, task_id, triggering_comment_id, target_persona, prompt_context, output,
		          status, retry_count, max_retries, attempts, last_error,
		          created_at, updated_at, dispatched_at, completed_at, props
	`, id, output, completedAt).Scan(
		&w.ID, &w.TaskID, &w.TriggeringCommentID, &w.TargetPersona, &w.PromptContext, &w.Output,
		&w.Status, &w.RetryCount, &w.MaxRetries, &w.Attempts, &w.LastError,
		&w.CreatedAt, &w.UpdatedAt, &w.DispatchedAt, &w.CompletedAt, &w.Props,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &w, err
}

// RecordWorkItemAttempt appends an attempt entry, increments retry_count,
// flips status to 'failed', sets last_error. Only valid from 'dispatched'.
// `attempt` is the JSON object to append to attempts[].
func (s *Store) RecordWorkItemAttempt(ctx context.Context, id string, attempt json.RawMessage, errorMsg string, now int64) (*model.WorkItem, error) {
	var w model.WorkItem
	err := s.pool.QueryRow(ctx, `
		UPDATE work_items
		SET attempts = attempts || $2::jsonb,
		    retry_count = retry_count + 1,
		    status = 'failed',
		    last_error = $3,
		    updated_at = $4
		WHERE id = $1 AND status = 'dispatched'
		RETURNING id, task_id, triggering_comment_id, target_persona, prompt_context, output,
		          status, retry_count, max_retries, attempts, last_error,
		          created_at, updated_at, dispatched_at, completed_at, props
	`, id, attempt, errorMsg, now).Scan(
		&w.ID, &w.TaskID, &w.TriggeringCommentID, &w.TargetPersona, &w.PromptContext, &w.Output,
		&w.Status, &w.RetryCount, &w.MaxRetries, &w.Attempts, &w.LastError,
		&w.CreatedAt, &w.UpdatedAt, &w.DispatchedAt, &w.CompletedAt, &w.Props,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &w, err
}

func (s *Store) scanWorkItems(ctx context.Context, query string, args ...any) ([]model.WorkItem, error) {
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var items []model.WorkItem
	for rows.Next() {
		var w model.WorkItem
		if err := rows.Scan(
			&w.ID, &w.TaskID, &w.TriggeringCommentID, &w.TargetPersona, &w.PromptContext, &w.Output,
			&w.Status, &w.RetryCount, &w.MaxRetries, &w.Attempts, &w.LastError,
			&w.CreatedAt, &w.UpdatedAt, &w.DispatchedAt, &w.CompletedAt, &w.Props,
		); err != nil {
			return nil, err
		}
		items = append(items, w)
	}
	return items, rows.Err()
}

// ─── Knowledge Cards ──────────────────────────────────────────────────────

// CreateKnowledgeCard inserts a card. Returns a clear error if the slug id
// already exists (the handler maps it to 409).
func (s *Store) CreateKnowledgeCard(ctx context.Context, c *model.KnowledgeCard) error {
	_, err := s.pool.Exec(ctx, `
		INSERT INTO knowledge_cards (id, content, tags, is_valid, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6)
	`, c.ID, c.Content, c.Tags, c.IsValid, c.CreatedAt, c.UpdatedAt)
	return err
}

func (s *Store) GetKnowledgeCard(ctx context.Context, id string) (*model.KnowledgeCard, error) {
	var c model.KnowledgeCard
	err := s.pool.QueryRow(ctx, `
		SELECT id, content, tags, is_valid, created_at, updated_at
		FROM knowledge_cards WHERE id = $1
	`, id).Scan(&c.ID, &c.Content, &c.Tags, &c.IsValid, &c.CreatedAt, &c.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &c, err
}

// ListKnowledgeCards returns cards, optionally filtered by tag. Invalid cards
// are excluded unless includeInvalid is true.
func (s *Store) ListKnowledgeCards(ctx context.Context, tag *string, includeInvalid bool) ([]model.KnowledgeCard, error) {
	return s.scanKnowledgeCards(ctx, `
		SELECT id, content, tags, is_valid, created_at, updated_at
		FROM knowledge_cards
		WHERE ($1::text IS NULL OR $1 = ANY(tags))
		  AND (is_valid OR $2)
		ORDER BY updated_at DESC
	`, tag, includeInvalid)
}

// SearchKnowledgeCards runs full-text search over content (when q is
// non-empty), optionally filtered by tag, ranked by relevance. Invalid cards
// excluded unless includeInvalid. An empty q with a tag is a tag-only listing.
//
// Recall over precision: a knowledge base should surface a relevant card even
// when the query has extra words the card doesn't contain. plainto_tsquery
// ANDs every term, so one missing word excludes the whole card — bad for the
// natural-language queries personas make. We instead match on OR (any term)
// and let ts_rank order by how well each card matches. The OR query is
// derived by rewriting plainto_tsquery's safe lexeme output ('a & b & c')
// into 'a | b | c' — keeps plainto's robust input handling, swaps the
// connective.
func (s *Store) SearchKnowledgeCards(ctx context.Context, q string, tag *string, includeInvalid bool, limit int) ([]model.KnowledgeCard, error) {
	if limit <= 0 {
		limit = 10
	}
	return s.scanKnowledgeCards(ctx, `
		SELECT id, content, tags, is_valid, created_at, updated_at
		FROM knowledge_cards
		WHERE ($1 = '' OR to_tsvector('english', coalesce(content,'')) @@
		       replace(plainto_tsquery('english', $1)::text, '&', '|')::tsquery)
		  AND ($2::text IS NULL OR $2 = ANY(tags))
		  AND (is_valid OR $3)
		ORDER BY
			CASE WHEN $1 = '' THEN 0
			     ELSE ts_rank(
			         to_tsvector('english', coalesce(content,'')),
			         replace(plainto_tsquery('english', $1)::text, '&', '|')::tsquery
			     )
			END DESC,
			updated_at DESC
		LIMIT $4
	`, q, tag, includeInvalid, limit)
}

// UpdateKnowledgeCard applies a partial update. nil fields are left unchanged.
// Returns (nil, nil) on not-found.
func (s *Store) UpdateKnowledgeCard(ctx context.Context, id string, req *model.UpdateKnowledgeCardRequest, updatedAt int64) (*model.KnowledgeCard, error) {
	setClauses := []string{"updated_at = @updated_at"}
	args := pgx.NamedArgs{"id": id, "updated_at": updatedAt}

	if req.Content != nil {
		setClauses = append(setClauses, "content = @content")
		args["content"] = *req.Content
	}
	if req.Tags != nil {
		setClauses = append(setClauses, "tags = @tags")
		args["tags"] = req.Tags
	}
	if req.IsValid != nil {
		setClauses = append(setClauses, "is_valid = @is_valid")
		args["is_valid"] = *req.IsValid
	}

	query := fmt.Sprintf(`
		UPDATE knowledge_cards SET %s WHERE id = @id
		RETURNING id, content, tags, is_valid, created_at, updated_at
	`, joinStrings(setClauses, ", "))

	var c model.KnowledgeCard
	err := s.pool.QueryRow(ctx, query, args).Scan(
		&c.ID, &c.Content, &c.Tags, &c.IsValid, &c.CreatedAt, &c.UpdatedAt,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	return &c, err
}

func (s *Store) DeleteKnowledgeCard(ctx context.Context, id string) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM knowledge_cards WHERE id = $1`, id)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return pgx.ErrNoRows
	}
	return nil
}

func (s *Store) scanKnowledgeCards(ctx context.Context, query string, args ...any) ([]model.KnowledgeCard, error) {
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var cards []model.KnowledgeCard
	for rows.Next() {
		var c model.KnowledgeCard
		if err := rows.Scan(&c.ID, &c.Content, &c.Tags, &c.IsValid, &c.CreatedAt, &c.UpdatedAt); err != nil {
			return nil, err
		}
		cards = append(cards, c)
	}
	return cards, rows.Err()
}

// ─── Helpers ────────────────────────────────────────────────────────────────

func joinStrings(s []string, sep string) string {
	result := ""
	for i, v := range s {
		if i > 0 {
			result += sep
		}
		result += v
	}
	return result
}

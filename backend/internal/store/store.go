package store

import (
	"context"
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
		SELECT c.id, c.task_id, c.parent_comment_id, c.text, c.comment_type, c.created_by, c.proposal_status, c.proposal_feedback, c.created_at, c.updated_at
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
		SELECT c.id, c.task_id, c.parent_comment_id, c.text, c.comment_type, c.created_by, c.proposal_status, c.proposal_feedback, c.created_at, c.updated_at
		FROM comments c JOIN tasks t ON c.task_id = t.id
		WHERE c.id = $1 AND t.user_id = $2
	`, commentID, userID).Scan(&c.ID, &c.TaskID, &c.ParentCommentID, &c.Text, &c.CommentType, &c.CreatedBy, &c.ProposalStatus, &c.ProposalFeedback, &c.CreatedAt, &c.UpdatedAt)
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

	_, err = s.pool.Exec(ctx, `
		INSERT INTO comments (id, task_id, parent_comment_id, text, comment_type, created_by, proposal_status, proposal_feedback, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
	`, c.ID, c.TaskID, c.ParentCommentID, c.Text, c.CommentType, c.CreatedBy, c.ProposalStatus, c.ProposalFeedback, c.CreatedAt, c.UpdatedAt)
	return err
}

func (s *Store) UpdateProposalStatus(ctx context.Context, userID, commentID, status string, feedback *string, updatedAt int64) (*model.Comment, error) {
	var c model.Comment
	err := s.pool.QueryRow(ctx, `
		UPDATE comments SET proposal_status = $1, proposal_feedback = $2, updated_at = $3
		WHERE id = $4 AND comment_type = 'PROPOSAL'
		AND task_id IN (SELECT id FROM tasks WHERE user_id = $5)
		RETURNING id, task_id, parent_comment_id, text, comment_type, created_by, proposal_status, proposal_feedback, created_at, updated_at
	`, status, feedback, updatedAt, commentID, userID).Scan(
		&c.ID, &c.TaskID, &c.ParentCommentID, &c.Text, &c.CommentType, &c.CreatedBy, &c.ProposalStatus, &c.ProposalFeedback, &c.CreatedAt, &c.UpdatedAt,
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
		RETURNING id, task_id, parent_comment_id, text, comment_type, created_by, proposal_status, proposal_feedback, created_at, updated_at
	`, status, feedback, updatedAt, commentID).Scan(
		&c.ID, &c.TaskID, &c.ParentCommentID, &c.Text, &c.CommentType, &c.CreatedBy, &c.ProposalStatus, &c.ProposalFeedback, &c.CreatedAt, &c.UpdatedAt,
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
		if err := rows.Scan(&c.ID, &c.TaskID, &c.ParentCommentID, &c.Text, &c.CommentType, &c.CreatedBy, &c.ProposalStatus, &c.ProposalFeedback, &c.CreatedAt, &c.UpdatedAt); err != nil {
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
		SELECT c.id, c.task_id, c.parent_comment_id, c.text, c.comment_type, c.created_by, c.proposal_status, c.proposal_feedback, c.created_at, c.updated_at
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

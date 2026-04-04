import { useState, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { CommentEntity } from '../types';
import { useTasks } from '../hooks/useTasks';
import { formatDate } from '../utils';
import styles from './CommentSection.module.css';

interface Props {
  taskId: string;
}

/** Build a map from parentCommentId -> child comments */
function buildThreadMap(comments: CommentEntity[]): Map<string | null, CommentEntity[]> {
  const map = new Map<string | null, CommentEntity[]>();
  for (const c of comments) {
    const key = c.parentCommentId ?? null;
    const list = map.get(key);
    if (list) {
      list.push(c);
    } else {
      map.set(key, [c]);
    }
  }
  return map;
}

function CommentNode({
  comment,
  threadMap,
  depth,
  taskId,
  onReply,
  onDelete,
  onApprove,
  onDeny,
}: {
  comment: CommentEntity;
  threadMap: Map<string | null, CommentEntity[]>;
  depth: number;
  taskId: string;
  onReply: (parentId: string) => void;
  onDelete: (commentId: string) => void;
  onApprove: (commentId: string) => void;
  onDeny: (commentId: string) => void;
}) {
  const children = threadMap.get(comment.id) ?? [];
  const isAgent = comment.createdBy !== 'user';
  const isProposal = comment.commentType === 'PROPOSAL';
  const isPending = isProposal && comment.proposalStatus === 'PENDING';

  return (
    <div
      className={styles.threadNode}
      style={{ marginLeft: depth > 0 ? 20 : 0 }}
    >
      <div
        className={`${styles.comment} ${isProposal ? styles.proposalComment : ''}`}
      >
        <div className={styles.commentContent}>
          {/* Badges row */}
          <div className={styles.badgeRow}>
            {isAgent && (
              <span className={styles.agentBadge}>Agent</span>
            )}
            {isProposal && (
              <span className={styles.proposalBadge}>Proposal</span>
            )}
            {isProposal && comment.proposalStatus && (
              <span
                className={`${styles.statusBadge} ${
                  comment.proposalStatus === 'APPROVED'
                    ? styles.statusApproved
                    : comment.proposalStatus === 'DENIED'
                      ? styles.statusDenied
                      : styles.statusPending
                }`}
              >
                {comment.proposalStatus}
              </span>
            )}
          </div>

          <div className={styles.commentText}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{comment.text}</ReactMarkdown>
          </div>

          {/* Show proposal feedback if present */}
          {isProposal && comment.proposalFeedback && (
            <div className={styles.proposalFeedback}>
              Feedback: {comment.proposalFeedback}
            </div>
          )}

          <div className={styles.commentMeta}>
            <span className={styles.commentDate}>
              {formatDate(comment.createdAt)}
            </span>
            <span className={styles.commentCreator}>
              by {isAgent ? comment.createdBy : 'you'}
            </span>
          </div>

          {/* Action buttons */}
          <div className={styles.commentActions}>
            <button
              className={styles.replyButton}
              onClick={() => onReply(comment.id)}
            >
              Reply
            </button>
            {isPending && (
              <>
                <button
                  className={styles.approveButton}
                  onClick={() => onApprove(comment.id)}
                >
                  Approve
                </button>
                <button
                  className={styles.denyButton}
                  onClick={() => onDeny(comment.id)}
                >
                  Deny
                </button>
              </>
            )}
          </div>
        </div>
        <button
          className={styles.deleteButton}
          onClick={() => onDelete(comment.id)}
          aria-label="Delete comment"
        >
          &#128465;
        </button>
      </div>

      {/* Render children */}
      {children.map((child) => (
        <CommentNode
          key={child.id}
          comment={child}
          threadMap={threadMap}
          depth={depth + 1}
          taskId={taskId}
          onReply={onReply}
          onDelete={onDelete}
          onApprove={onApprove}
          onDeny={onDeny}
        />
      ))}
    </div>
  );
}

export default function CommentSection({ taskId }: Props) {
  const {
    getCommentsForTask,
    fetchCommentsForTask,
    addComment,
    deleteComment,
    approveProposal,
    denyProposal,
  } = useTasks();
  const [text, setText] = useState('');
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [denyCommentId, setDenyCommentId] = useState<string | null>(null);
  const [denyFeedback, setDenyFeedback] = useState('');
  const comments = getCommentsForTask(taskId);

  // Fetch comments from API on mount and auto-refresh every 10s
  useEffect(() => {
    fetchCommentsForTask(taskId);
    const interval = setInterval(() => fetchCommentsForTask(taskId), 10_000);
    return () => clearInterval(interval);
  }, [taskId, fetchCommentsForTask]);

  const threadMap = buildThreadMap(comments);
  const rootComments = threadMap.get(null) ?? [];

  const replyingToComment = replyingTo
    ? comments.find((c) => c.id === replyingTo)
    : null;

  const handleAdd = async () => {
    if (!text.trim()) return;
    await addComment(taskId, text.trim(), {
      parentCommentId: replyingTo ?? undefined,
    });
    setText('');
    setReplyingTo(null);
  };

  const handleDelete = async (commentId: string) => {
    if (window.confirm('Delete this comment?')) {
      await deleteComment(commentId);
    }
  };

  const handleApprove = useCallback(
    async (commentId: string) => {
      await approveProposal(commentId);
    },
    [approveProposal],
  );

  const handleDenyStart = useCallback((commentId: string) => {
    setDenyCommentId(commentId);
    setDenyFeedback('');
  }, []);

  const handleDenyConfirm = useCallback(async () => {
    if (!denyCommentId) return;
    await denyProposal(denyCommentId, denyFeedback.trim() || undefined);
    setDenyCommentId(null);
    setDenyFeedback('');
  }, [denyCommentId, denyFeedback, denyProposal]);

  const handleDenyCancel = useCallback(() => {
    setDenyCommentId(null);
    setDenyFeedback('');
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAdd();
    }
  };

  return (
    <div className={styles.section}>
      <h3 className={styles.header}>Comments ({comments.length})</h3>

      {/* Reply indicator */}
      {replyingToComment && (
        <div className={styles.replyIndicator}>
          <span>
            Replying to: &ldquo;{replyingToComment.text.slice(0, 60)}
            {replyingToComment.text.length > 60 ? '...' : ''}&rdquo;
          </span>
          <button
            className={styles.cancelReply}
            onClick={() => setReplyingTo(null)}
          >
            Cancel
          </button>
        </div>
      )}

      <div className={styles.addForm}>
        <input
          className={styles.addInput}
          type="text"
          placeholder={replyingTo ? 'Write a reply...' : 'Add a comment...'}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          className={styles.sendButton}
          onClick={handleAdd}
          disabled={!text.trim()}
        >
          Send
        </button>
      </div>

      {/* Deny feedback modal */}
      {denyCommentId && (
        <div className={styles.denyModal}>
          <div className={styles.denyModalContent}>
            <div className={styles.denyModalTitle}>Deny Proposal</div>
            <input
              className={styles.addInput}
              type="text"
              placeholder="Feedback (optional)..."
              value={denyFeedback}
              onChange={(e) => setDenyFeedback(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleDenyConfirm();
                }
              }}
              autoFocus
            />
            <div className={styles.denyModalActions}>
              <button className={styles.replyButton} onClick={handleDenyCancel}>
                Cancel
              </button>
              <button className={styles.denyButton} onClick={handleDenyConfirm}>
                Deny
              </button>
            </div>
          </div>
        </div>
      )}

      <div className={styles.list}>
        {rootComments.length === 0 && (
          <div className={styles.empty}>No comments yet</div>
        )}
        {rootComments.map((comment) => (
          <CommentNode
            key={comment.id}
            comment={comment}
            threadMap={threadMap}
            depth={0}
            taskId={taskId}
            onReply={setReplyingTo}
            onDelete={handleDelete}
            onApprove={handleApprove}
            onDeny={handleDenyStart}
          />
        ))}
      </div>
    </div>
  );
}

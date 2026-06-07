import { useState, useEffect, useCallback, useRef } from 'react';
import Markdown from './Markdown';
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

function Composer({
  value,
  onChange,
  onSubmit,
  onCancel,
  placeholder,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onCancel?: () => void;
  placeholder: string;
  autoFocus?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus && ref.current) {
      ref.current.focus();
      // Place caret at end
      const len = ref.current.value.length;
      ref.current.setSelectionRange(len, len);
    }
  }, [autoFocus]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (value.trim()) onSubmit();
    } else if (e.key === 'Escape' && onCancel) {
      e.preventDefault();
      onCancel();
    }
  };

  return (
    <div className={styles.composer}>
      <textarea
        ref={ref}
        className={styles.composerTextarea}
        rows={5}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <div className={styles.composerActions}>
        {onCancel && (
          <button className={styles.replyButton} onClick={onCancel}>
            Cancel
          </button>
        )}
        <button
          className={styles.sendButton}
          onClick={onSubmit}
          disabled={!value.trim()}
        >
          Send
        </button>
        <span className={styles.composerHint}>⌘+Enter to send</span>
      </div>
    </div>
  );
}

function CommentNode({
  comment,
  threadMap,
  depth,
  taskId,
  replyingTo,
  replyText,
  onStartReply,
  onCancelReply,
  onChangeReplyText,
  onSubmitReply,
  onDelete,
  onApprove,
  onDeny,
}: {
  comment: CommentEntity;
  threadMap: Map<string | null, CommentEntity[]>;
  depth: number;
  taskId: string;
  replyingTo: string | null;
  replyText: string;
  onStartReply: (parentId: string) => void;
  onCancelReply: () => void;
  onChangeReplyText: (v: string) => void;
  onSubmitReply: () => void;
  onDelete: (commentId: string) => void;
  onApprove: (commentId: string) => void;
  onDeny: (commentId: string) => void;
}) {
  const children = threadMap.get(comment.id) ?? [];
  const isAgent = comment.createdBy !== 'user';
  const isProposal = comment.commentType === 'PROPOSAL';
  const isPending = isProposal && comment.proposalStatus === 'PENDING';
  const isReplyingHere = replyingTo === comment.id;
  void taskId;

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

          <Markdown>{comment.text}</Markdown>

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
              onClick={() => (isReplyingHere ? onCancelReply() : onStartReply(comment.id))}
            >
              {isReplyingHere ? 'Cancel reply' : 'Reply'}
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
          replyingTo={replyingTo}
          replyText={replyText}
          onStartReply={onStartReply}
          onCancelReply={onCancelReply}
          onChangeReplyText={onChangeReplyText}
          onSubmitReply={onSubmitReply}
          onDelete={onDelete}
          onApprove={onApprove}
          onDeny={onDeny}
        />
      ))}

      {/* Inline reply composer: rendered after children, indented one level deeper
          to match where the new reply will land in the tree. */}
      {isReplyingHere && (
        <div
          className={styles.inlineComposer}
          style={{ marginLeft: 20 }}
        >
          <Composer
            value={replyText}
            onChange={onChangeReplyText}
            onSubmit={onSubmitReply}
            onCancel={onCancelReply}
            placeholder="Write a reply…"
            autoFocus
          />
        </div>
      )}
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
  const [topText, setTopText] = useState('');
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyText, setReplyText] = useState('');
  const [denyCommentId, setDenyCommentId] = useState<string | null>(null);
  const [denyFeedback, setDenyFeedback] = useState('');
  const comments = getCommentsForTask(taskId);

  // Fetch comments from API on mount and auto-refresh every 3s
  useEffect(() => {
    fetchCommentsForTask(taskId);
    const interval = setInterval(() => fetchCommentsForTask(taskId), 3_000);
    return () => clearInterval(interval);
  }, [taskId, fetchCommentsForTask]);

  const threadMap = buildThreadMap(comments);
  const rootComments = threadMap.get(null) ?? [];

  const handleStartReply = useCallback((parentId: string) => {
    // Silent discard of any in-progress reply on switch.
    setReplyingTo(parentId);
    setReplyText('');
  }, []);

  const handleCancelReply = useCallback(() => {
    setReplyingTo(null);
    setReplyText('');
  }, []);

  const handleSubmitReply = useCallback(async () => {
    if (!replyingTo) return;
    const text = replyText.trim();
    if (!text) return;
    await addComment(taskId, text, { parentCommentId: replyingTo });
    setReplyText('');
    setReplyingTo(null);
  }, [addComment, replyText, replyingTo, taskId]);

  const handleAddTopLevel = useCallback(async () => {
    const text = topText.trim();
    if (!text) return;
    await addComment(taskId, text);
    setTopText('');
  }, [addComment, taskId, topText]);

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

  return (
    <div className={styles.section}>
      <h3 className={styles.header}>Comments ({comments.length})</h3>

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
            replyingTo={replyingTo}
            replyText={replyText}
            onStartReply={handleStartReply}
            onCancelReply={handleCancelReply}
            onChangeReplyText={setReplyText}
            onSubmitReply={handleSubmitReply}
            onDelete={handleDelete}
            onApprove={handleApprove}
            onDeny={handleDenyStart}
          />
        ))}
      </div>

      {/* Top-level composer pinned at bottom (chat convention). */}
      <div className={styles.bottomComposer}>
        <Composer
          value={topText}
          onChange={setTopText}
          onSubmit={handleAddTopLevel}
          placeholder="Add a comment…"
        />
      </div>
    </div>
  );
}

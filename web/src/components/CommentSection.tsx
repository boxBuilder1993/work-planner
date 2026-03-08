import { useState } from 'react';
import { useTasks } from '../hooks/useTasks';
import { formatDate } from '../utils';
import styles from './CommentSection.module.css';

interface Props {
  taskId: string;
}

export default function CommentSection({ taskId }: Props) {
  const { getCommentsForTask, addComment, deleteComment } = useTasks();
  const [text, setText] = useState('');
  const comments = getCommentsForTask(taskId);

  const handleAdd = () => {
    if (!text.trim()) return;
    addComment(taskId, text.trim());
    setText('');
  };

  const handleDelete = (commentId: string) => {
    if (window.confirm('Delete this comment?')) {
      deleteComment(commentId);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAdd();
    }
  };

  return (
    <div className={styles.section}>
      <h3 className={styles.header}>Comments ({comments.length})</h3>
      <div className={styles.list}>
        {comments.length === 0 && (
          <div className={styles.empty}>No comments yet</div>
        )}
        {comments.map((comment) => (
          <div key={comment.id} className={styles.comment}>
            <div className={styles.commentContent}>
              <div className={styles.commentText}>{comment.text}</div>
              <div className={styles.commentDate}>
                {formatDate(comment.createdAt)}
              </div>
            </div>
            <button
              className={styles.deleteButton}
              onClick={() => handleDelete(comment.id)}
              aria-label="Delete comment"
            >
              &#128465;
            </button>
          </div>
        ))}
      </div>
      <div className={styles.addForm}>
        <input
          className={styles.addInput}
          type="text"
          placeholder="Add a comment..."
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
    </div>
  );
}

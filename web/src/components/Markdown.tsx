import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from './Markdown.module.css';

/**
 * Renders a blob of GitHub-flavored markdown with consistent prose styling.
 * Use this everywhere user/AI text is displayed — task descriptions, comments,
 * knowledge-card content — so markdown renders the same way across the app.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className={styles.markdown}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

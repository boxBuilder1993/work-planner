import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Markdown from './Markdown';
import {
  type KnowledgeCard,
  listCards,
  searchCards,
  createCard,
  updateCard,
  deleteCard,
} from '../api/knowledge';
import { ApiError } from '../api/client';
import styles from './KnowledgeCards.module.css';

type EditorState =
  | { mode: 'closed' }
  | { mode: 'new' }
  | { mode: 'edit'; card: KnowledgeCard };

export default function KnowledgeCards() {
  const navigate = useNavigate();
  const [cards, setCards] = useState<KnowledgeCard[]>([]);
  const [query, setQuery] = useState('');
  const [includeInvalid, setIncludeInvalid] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState>({ mode: 'closed' });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const q = query.trim();
      const result = q
        ? await searchCards(q, { includeInvalid, limit: 100 })
        : await listCards({ includeInvalid });
      setCards(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load cards');
    } finally {
      setLoading(false);
    }
  }, [query, includeInvalid]);

  // Debounced reload as the search query / filter changes.
  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <button className={styles.backButton} onClick={() => navigate(-1)} aria-label="Back">
          &larr;
        </button>
        <span className={styles.topBarTitle}>Knowledge Cards</span>
        <button className={styles.newButton} onClick={() => setEditor({ mode: 'new' })}>
          + New
        </button>
      </div>

      <div className={styles.content}>
        <div className={styles.searchRow}>
          <input
            className={styles.search}
            type="search"
            placeholder="Search cards…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <label className={styles.invalidToggle}>
            <input
              type="checkbox"
              checked={includeInvalid}
              onChange={(e) => setIncludeInvalid(e.target.checked)}
            />
            Show invalid
          </label>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        {editor.mode !== 'closed' && (
          <CardEditor
            key={editor.mode === 'edit' ? editor.card.id : 'new'}
            initial={editor.mode === 'edit' ? editor.card : null}
            onClose={() => setEditor({ mode: 'closed' })}
            onSaved={() => {
              setEditor({ mode: 'closed' });
              void load();
            }}
          />
        )}

        {loading && cards.length === 0 ? (
          <p className={styles.muted}>Loading…</p>
        ) : cards.length === 0 ? (
          <p className={styles.muted}>
            {query ? 'No cards match your search.' : 'No cards yet — create one.'}
          </p>
        ) : (
          cards.map((c) => (
            <CardView
              key={c.id}
              card={c}
              onEdit={() => setEditor({ mode: 'edit', card: c })}
              onDeleted={load}
            />
          ))
        )}
      </div>
    </div>
  );
}

function CardView({
  card,
  onEdit,
  onDeleted,
}: {
  card: KnowledgeCard;
  onEdit: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);

  const handleDelete = async () => {
    if (!window.confirm(`Delete card "${card.id}"? This can't be undone.`)) return;
    setBusy(true);
    try {
      await deleteCard(card.id);
      onDeleted();
    } catch {
      window.alert('Failed to delete card');
      setBusy(false);
    }
  };

  return (
    <div className={`${styles.card} ${card.isValid ? '' : styles.invalidCard}`}>
      <div className={styles.cardHead}>
        <span className={styles.cardId}>{card.id}</span>
        {!card.isValid && <span className={styles.invalidBadge}>invalid</span>}
        <div className={styles.cardActions}>
          <button className={styles.linkButton} onClick={onEdit}>
            Edit
          </button>
          <button className={styles.linkButtonDanger} onClick={handleDelete} disabled={busy}>
            Delete
          </button>
        </div>
      </div>
      {card.tags.length > 0 && (
        <div className={styles.tags}>
          {card.tags.map((t) => (
            <span key={t} className={styles.tag}>
              {t}
            </span>
          ))}
        </div>
      )}
      <div className={styles.cardContent}>
        <Markdown>{card.content}</Markdown>
      </div>
    </div>
  );
}

function CardEditor({
  initial,
  onClose,
  onSaved,
}: {
  initial: KnowledgeCard | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const editing = initial !== null;
  const [id, setId] = useState(initial?.id ?? '');
  const [content, setContent] = useState(initial?.content ?? '');
  const [tagsInput, setTagsInput] = useState((initial?.tags ?? []).join(', '));
  const [isValid, setIsValid] = useState(initial?.isValid ?? true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
    setSaving(true);
    setErr(null);
    try {
      if (editing) {
        await updateCard(initial.id, { content, tags, isValid });
      } else {
        await createCard({ id: id.trim(), content, tags });
      }
      onSaved();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : 'Failed to save');
      setSaving(false);
    }
  };

  return (
    <form className={styles.editor} onSubmit={handleSave}>
      <div className={styles.editorHead}>
        <strong>{editing ? `Edit ${initial.id}` : 'New card'}</strong>
        <button type="button" className={styles.linkButton} onClick={onClose}>
          Cancel
        </button>
      </div>

      {!editing && (
        <label className={styles.field}>
          <span className={styles.label}>Slug (id)</span>
          <input
            className={styles.input}
            placeholder="lowercase-hyphenated"
            value={id}
            onChange={(e) => setId(e.target.value)}
            required
            autoFocus
          />
        </label>
      )}

      <label className={styles.field}>
        <span className={styles.label}>Content</span>
        <textarea
          className={styles.textarea}
          rows={6}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          required
        />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Tags (comma-separated)</span>
        <input
          className={styles.input}
          placeholder="area, topic"
          value={tagsInput}
          onChange={(e) => setTagsInput(e.target.value)}
        />
      </label>

      {editing && (
        <label className={styles.checkboxField}>
          <input
            type="checkbox"
            checked={isValid}
            onChange={(e) => setIsValid(e.target.checked)}
          />
          Valid (uncheck to retire without deleting)
        </label>
      )}

      {err && <p className={styles.error}>{err}</p>}

      <button
        className={styles.primaryButton}
        type="submit"
        disabled={saving || !content.trim() || (!editing && !id.trim())}
      >
        {saving ? 'Saving…' : editing ? 'Save' : 'Create'}
      </button>
    </form>
  );
}

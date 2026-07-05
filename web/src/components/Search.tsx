import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { searchTasks } from '../api/tasks';
import type { TaskEntity } from '../types';
import { Search as SearchIcon } from 'lucide-react';

export default function Search() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [results, setResults] = useState<TaskEntity[]>([]);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    const query = q.trim();
    const id = setTimeout(() => {
      if (!query) { setResults([]); setSearched(false); return; }
      searchTasks(query).then((r) => { setResults(r); setSearched(true); }).catch(() => { setResults([]); setSearched(true); });
    }, query ? 250 : 0);
    return () => clearTimeout(id);
  }, [q]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-3 border-b px-7 py-4">
        <h1 className="text-[19px] font-semibold tracking-tight">Search</h1>
      </header>
      <div className="mx-auto w-full max-w-2xl p-7">
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search tasks by title or description…"
            className="h-11 w-full rounded-lg border bg-background pl-10 pr-3 text-[14px] outline-none focus:border-foreground"
          />
        </div>

        <div className="mt-4 space-y-1.5">
          {searched && results.length === 0 && <p className="px-1 text-sm text-muted-foreground">No matches.</p>}
          {results.map((t) => (
            <button
              key={t.id}
              onClick={() => navigate(`/projects/${t.id}`)}
              className="flex w-full items-center gap-3 rounded-lg border px-3.5 py-2.5 text-left hover:bg-muted"
            >
              <span className="flex-1">
                <span className="text-[14px] font-medium">{t.title}</span>
                {t.description && <span className="mt-0.5 block truncate text-[12.5px] text-muted-foreground">{t.description}</span>}
              </span>
              <span className="shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                {t.status === 'CLOSED' ? 'Done' : 'Open'}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

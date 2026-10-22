import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Book, type SortKey } from "../api";
import { AddBookDialog } from "../components/AddBookDialog";
import { BookCard } from "../components/BookCard";
import { DeleteDialog, ReindexDialog } from "../components/ConfirmDialogs";
import { Icon } from "../components/Icon";
import { Menu } from "../components/Menu";
import { useDebounced } from "../lib/hooks";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "title", label: "Title" },
  { key: "added", label: "Date added" },
  { key: "opened", label: "Last opened" },
];

export function Library({ onOpen }: { onOpen: (bookId: string) => void }) {
  const [books, setBooks] = useState<Book[] | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("added");
  const [sortOpen, setSortOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [toDelete, setToDelete] = useState<Book | null>(null);
  const [toReindex, setToReindex] = useState<Book | null>(null);
  const sortBtn = useRef<HTMLButtonElement>(null);
  const q = useDebounced(query, 250);

  const refresh = useCallback(async () => {
    setBooks(await api.listBooks({ query: q, sort }));
  }, [q, sort]);

  useEffect(() => {
    void refresh();
    return api.onLibraryChange(() => void refresh());
  }, [refresh]);

  const empty = books !== null && books.length === 0;

  return (
    <div className="or app-library">
      <header className="app-library__header">
        <div className="app-name">Orange Reader</div>
        <div className="or-search app-library__search">
          <Icon name="search" />
          <input
            className="or-input"
            placeholder="Search your library"
            aria-label="Search your library"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <button
          ref={sortBtn}
          type="button"
          className="or-select"
          aria-haspopup="menu"
          aria-expanded={sortOpen}
          onClick={() => setSortOpen((v) => !v)}
        >
          {SORTS.find((s) => s.key === sort)?.label}
          <Icon name="chevronDown" />
        </button>
        {sortOpen && sortBtn.current && (
          <Menu
            anchor={sortBtn.current}
            align="left"
            radio
            onClose={() => setSortOpen(false)}
            items={SORTS.map((s) => ({ label: s.label, selected: s.key === sort, onSelect: () => setSort(s.key) }))}
          />
        )}
        <button type="button" className="or-btn or-btn--primary" onClick={() => setAdding(true)}>
          <Icon name="plus" />
          Add book
        </button>
      </header>

      <main className="app-library__main">
        {empty && !q && (
          <div className="app-empty">
            <p className="app-empty__title">Your library is empty</p>
            <p className="or-cap">Add a PDF to start reading.</p>
          </div>
        )}
        {empty && q && (
          <div className="app-empty">
            <p className="or-cap">No books match '{q}'.</p>
          </div>
        )}
        {books && books.length > 0 && (
          <div className="app-grid">
            {books.map((b) => (
              <BookCard
                key={b.id}
                book={b}
                onOpen={() => onOpen(b.id)}
                onReindex={() => setToReindex(b)}
                onDelete={() => setToDelete(b)}
              />
            ))}
          </div>
        )}
      </main>

      {adding && <AddBookDialog onClose={() => setAdding(false)} onAdded={() => setSort("added")} />}
      {toDelete && (
        <DeleteDialog book={toDelete} onClose={() => setToDelete(null)} onConfirm={() => api.deleteBook(toDelete.id)} />
      )}
      {toReindex && (
        <ReindexDialog book={toReindex} onClose={() => setToReindex(null)} onConfirm={() => api.reindexBook(toReindex.id)} />
      )}
    </div>
  );
}

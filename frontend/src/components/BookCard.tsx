import { useEffect, useRef, useState } from "react";
import { api, type Book } from "../api";
import { useBookProgress } from "../lib/hooks";
import { Icon } from "./Icon";
import { Menu } from "./Menu";
import { FailedBadge, PreparingBadge, ReadyBadge } from "./Status";

function StandInPage({ title, author }: { title: string; author: string | null }) {
  return (
    <div className="or-page">
      <div className="or-page__kicker" />
      <div className="or-page__title">{title}</div>
      {author && <div className="or-page__author">{author}</div>}
      {Array.from({ length: 9 }, (_, i) => (
        <div key={i} className={`or-page__line${i % 4 === 3 ? " or-page__line--short" : ""}`} />
      ))}
    </div>
  );
}

export function BookCard({
  book,
  onOpen,
  onReindex,
  onDelete,
}: {
  book: Book;
  onOpen: () => void;
  onReindex: () => void;
  onDelete: () => void;
}) {
  const progress = useBookProgress(book.id, book);
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(book.title);
  const menuBtn = useRef<HTMLButtonElement>(null);
  const renameInput = useRef<HTMLInputElement>(null);
  const cardRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (renaming) renameInput.current?.select();
  }, [renaming]);

  const preparing = progress.status === "indexing";

  const saveRename = async () => {
    const title = draft.trim();
    setRenaming(false);
    if (title && title !== book.title) await api.updateBook(book.id, { title });
    cardRef.current?.focus();
  };

  return (
    <article
      ref={cardRef}
      className={`or-card${preparing ? " is-preparing" : ""}`}
      tabIndex={0}
      aria-label={book.title}
      onClick={() => !renaming && onOpen()}
      onKeyDown={(e) => {
        if (e.key === "Enter" && e.target === e.currentTarget) onOpen();
      }}
    >
      <div className="or-card__cover">
        {book.cover ? (
          <img className="app-cover" src={book.cover} alt="" />
        ) : (
          <StandInPage title={book.title} author={book.author} />
        )}
        {preparing && (
          <div className="or-card__bar" role="progressbar" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100}>
            <div className="or-progress__fill" style={{ width: `${progress.percent}%` }} />
          </div>
        )}
      </div>
      <button
        ref={menuBtn}
        type="button"
        className="or-btn or-btn--ghost or-btn--icon or-card__menu"
        aria-label="More actions"
        title="More actions"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpen((v) => !v);
        }}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <Icon name="more" />
      </button>
      {menuOpen && menuBtn.current && (
        <Menu
          anchor={menuBtn.current}
          onClose={() => setMenuOpen(false)}
          items={[
            { label: "Open", icon: "open", onSelect: onOpen },
            {
              label: "Rename",
              icon: "rename",
              onSelect: () => {
                setDraft(book.title);
                setRenaming(true);
              },
            },
            { label: "Re-index", icon: "refresh", onSelect: onReindex },
            { label: "Delete", icon: "trash", danger: true, separatorBefore: true, onSelect: onDelete },
          ]}
        />
      )}
      <div className="or-card__body">
        {renaming ? (
          <input
            ref={renameInput}
            className="or-input app-rename"
            value={draft}
            aria-label="Title"
            onChange={(e) => setDraft(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Enter") void saveRename();
              if (e.key === "Escape") {
                setRenaming(false);
                cardRef.current?.focus();
              }
            }}
            onBlur={() => void saveRename()}
          />
        ) : (
          <div className="or-card__title" title={book.title}>
            {book.title}
          </div>
        )}
        {book.author && <div className="or-card__author">{book.author}</div>}
        <div className="or-card__meta">
          {progress.status === "ready" && (
            <>
              <span>{book.pageCount ? `Page ${book.lastPage} of ${book.pageCount}` : ""}</span>
              <ReadyBadge />
            </>
          )}
          {preparing && <PreparingBadge percent={progress.percent} />}
          {progress.status === "failed" && (
            <>
              <span title={progress.error ?? undefined}>
                <FailedBadge />
              </span>
              <button
                type="button"
                className="or-link app-small-link"
                onClick={(e) => {
                  e.stopPropagation();
                  void api.reindexBook(book.id);
                }}
              >
                Retry
              </button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}

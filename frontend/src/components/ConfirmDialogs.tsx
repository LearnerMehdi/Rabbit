import { useRef, useState } from "react";
import type { Book } from "../api";
import { truncate } from "../lib/format";
import { Dialog } from "./Dialog";
import { ErrorLine } from "./Status";

function Confirm({
  title,
  body,
  action,
  danger,
  onConfirm,
  onClose,
}: {
  title: string;
  body: string;
  action: string;
  danger?: boolean;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Dialog
      title={title}
      onClose={onClose}
      initialFocus={cancel}
      footer={
        <>
          <button ref={cancel} type="button" className="or-btn or-btn--secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className={`or-btn ${danger ? "or-btn--danger" : "or-btn--primary"}`}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm();
                onClose();
              } catch (e) {
                setError(e instanceof Error ? e.message : "Something went wrong. Try again.");
                setBusy(false);
              }
            }}
          >
            {action}
          </button>
        </>
      }
    >
      <p>{body}</p>
      {error && <ErrorLine>{error}</ErrorLine>}
    </Dialog>
  );
}

export function DeleteDialog({ book, onConfirm, onClose }: { book: Book; onConfirm: () => Promise<void>; onClose: () => void }) {
  return (
    <Confirm
      title={`Delete '${truncate(book.title)}'?`}
      body="This removes the book and its data."
      action="Delete"
      danger
      onConfirm={onConfirm}
      onClose={onClose}
    />
  );
}

export function ReindexDialog({ book, onConfirm, onClose }: { book: Book; onConfirm: () => Promise<void>; onClose: () => void }) {
  return (
    <Confirm
      title={`Re-index '${truncate(book.title)}'?`}
      body="The book is prepared again from the PDF. Reading still works; chat is paused until it's ready."
      action="Confirm"
      onConfirm={onConfirm}
      onClose={onClose}
    />
  );
}

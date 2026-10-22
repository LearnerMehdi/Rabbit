import { useRef, useState } from "react";
import { api, ApiError } from "../api";
import { formatSize, titleFromFileName } from "../lib/format";
import { inspectPdf, type PdfPreview } from "../pdf/pdf";
import { Dialog } from "./Dialog";
import { Icon } from "./Icon";
import { ErrorLine } from "./Status";

const NOT_PDF = "This file isn't a PDF. Choose a .pdf file.";
const ENCRYPTED = "This PDF is password-protected. Remove the password and choose it again.";

type Chosen = { file: File; preview: PdfPreview | null; inspecting: boolean };

export function AddBookDialog({ onClose, onAdded }: { onClose: () => void; onAdded: (bookId: string) => void }) {
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);

  const choose = async (file: File | undefined) => {
    if (!file) return;
    const looksPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
    if (!looksPdf) {
      setChosen(null);
      setError(NOT_PDF);
      return;
    }
    setError(null);
    setChosen({ file, preview: null, inspecting: true });
    setTitle(titleFromFileName(file.name));
    setAuthor("");
    try {
      const preview = await inspectPdf(file);
      setChosen({ file, preview, inspecting: false });
      if (preview.encrypted) return setError(ENCRYPTED);
      if (preview.title) setTitle(preview.title);
      if (preview.author) setAuthor(preview.author);
    } catch {
      setChosen(null);
      setError(NOT_PDF);
    }
  };

  const add = async () => {
    if (!chosen) return;
    setBusy(true);
    try {
      const book = await api.addBook(chosen.file, { title, author: author || null });
      onAdded(book.id);
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't add this book. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const canAdd = !!chosen && !chosen.inspecting && !!title.trim() && !error && !busy;
  const pages = chosen?.preview?.pageCount;

  return (
    <Dialog
      title="Add book"
      wide
      onClose={onClose}
      initialFocus={cancel}
      footer={
        <>
          <button ref={cancel} type="button" className="or-btn or-btn--secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="or-btn or-btn--primary" disabled={!canAdd} onClick={() => void add()}>
            Add to library
          </button>
        </>
      }
    >
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={(e) => {
          void choose(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {!chosen ? (
        <div className="or-stack" style={{ gap: "var(--space-2)" }}>
          <div
            className={`or-drop${dragOver ? " is-dragover" : ""}${error ? " is-error" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              void choose(e.dataTransfer.files[0]);
            }}
          >
            <Icon name="upload" />
            {dragOver ? (
              <>
                <div>
                  <strong style={{ fontWeight: 500 }}>Drop to add</strong>
                </div>
                <div className="or-cap">One PDF at a time</div>
              </>
            ) : (
              <>
                <div>
                  <strong style={{ fontWeight: 500 }}>Drop a PDF here</strong>
                </div>
                <div className="or-cap">or</div>
                <button type="button" className="or-btn or-btn--secondary" onClick={() => input.current?.click()}>
                  Choose PDF
                </button>
              </>
            )}
          </div>
          {error && <ErrorLine>{error}</ErrorLine>}
        </div>
      ) : (
        <>
          <div className="or-stack" style={{ gap: "var(--space-2)" }}>
            <div className="or-file">
              <div className="or-file__icon">PDF</div>
              <div className="or-file__name">
                <strong>{chosen.file.name}</strong>
                <span className="or-cap">
                  {chosen.inspecting
                    ? "Reading…"
                    : `${chosen.preview?.encrypted ? "Password-protected" : `${pages} ${pages === 1 ? "page" : "pages"}`} · ${formatSize(chosen.file.size)}`}
                </span>
              </div>
              <button type="button" className="or-link" onClick={() => input.current?.click()}>
                Change file
              </button>
            </div>
            {error && <ErrorLine>{error}</ErrorLine>}
          </div>
          <label className="or-field">
            <span className="or-label">Title</span>
            <input className="or-input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="or-field">
            <span className="or-label">
              Author <span className="or-cap">(optional)</span>
            </span>
            <input className="or-input" value={author} onChange={(e) => setAuthor(e.target.value)} />
          </label>
        </>
      )}
    </Dialog>
  );
}

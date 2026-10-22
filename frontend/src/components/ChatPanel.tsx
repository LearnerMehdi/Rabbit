import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, ApiError, type Book, type ChatAvailability } from "../api";
import { CHAT_UNAVAILABLE } from "../api/mock";
import { useBookProgress, useMockSettings } from "../lib/hooks";
import { Icon } from "./Icon";

type Msg =
  | { kind: "q"; text: string; id: number }
  | { kind: "a"; text: string; id: number }
  | { kind: "error"; question: string; text: string; id: number };

// conversations last while the app is open (per book), not across reloads
const threads = new Map<string, Msg[]>();
let nextId = 1;

export function ChatPanel({ book }: { book: Book }) {
  const progress = useBookProgress(book.id, book);
  const settings = useMockSettings();
  const [availability, setAvailability] = useState<ChatAvailability | null>(null);
  const [messages, setMessages] = useState<Msg[]>(() => threads.get(book.id) ?? []);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    void api.getChatAvailability().then(setAvailability);
  }, [settings.chatMode]);

  useEffect(() => {
    threads.set(book.id, messages);
  }, [book.id, messages]);

  // stay pinned to the newest message
  useLayoutEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [messages, pending]);

  // grow the textarea up to 160px
  useLayoutEffect(() => {
    const t = box.current;
    if (!t) return;
    t.style.height = "auto";
    t.style.height = `${Math.min(160, t.scrollHeight)}px`;
  }, [draft]);

  const ask = async (question: string) => {
    setPending(true);
    try {
      const { answer } = await api.askQuestion(book.id, question);
      setMessages((m) => [...m, { kind: "a", text: answer, id: nextId++ }]);
    } catch (e) {
      const text =
        e instanceof ApiError && e.code === "unavailable" ? CHAT_UNAVAILABLE : "Couldn't get an answer.";
      setMessages((m) => [...m, { kind: "error", question, text, id: nextId++ }]);
    } finally {
      setPending(false);
    }
  };

  const send = () => {
    const q = draft.trim();
    if (!q || pending) return;
    setDraft("");
    setMessages((m) => [...m, { kind: "q", text: q, id: nextId++ }]);
    void ask(q);
  };

  const retry = (msg: Extract<Msg, { kind: "error" }>) => {
    setMessages((m) => m.filter((x) => x.id !== msg.id));
    void ask(msg.question);
  };

  const ready = progress.status === "ready";
  const unavailable = availability === "unavailable";

  let note: React.ReactNode = null;
  if (progress.status === "indexing") {
    note = (
      <>
        <Icon name="spinner" spin />
        Preparing this book… {progress.percent}%
      </>
    );
  } else if (progress.status === "failed") {
    note = (
      <>
        This book couldn't be prepared.
        <button type="button" className="or-link" onClick={() => void api.reindexBook(book.id)}>
          Retry
        </button>
      </>
    );
  } else if (unavailable) {
    note = CHAT_UNAVAILABLE;
  }

  return (
    <section className="app-chat" aria-label="Chat">
      <div ref={list} className="app-chat__list">
        <div className="or-chat">
          {messages.length === 0 && !pending && (
            <div className="or-chat__empty">{ready && unavailable ? CHAT_UNAVAILABLE : "Ask anything about this book."}</div>
          )}
          {messages.map((m) =>
            m.kind === "q" ? (
              <p key={m.id} className="or-msg or-msg--q">
                {m.text}
              </p>
            ) : m.kind === "a" ? (
              <div key={m.id} className="or-msg or-msg--a">
                {m.text.split(/\n{2,}/).map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            ) : (
              <div key={m.id} className="or-msg-error" role="alert">
                {m.text}{" "}
                <button type="button" className="or-link" onClick={() => retry(m)}>
                  Try again.
                </button>
              </div>
            ),
          )}
          {pending && (
            <div className="or-thinking" role="status" aria-label="Thinking">
              <span />
              <span />
              <span />
            </div>
          )}
        </div>
      </div>
      <div className="app-chat__composer">
        {note || availability === null ? (
          <div className="or-composer is-disabled" aria-disabled="true">
            <div className="or-composer__note">{note}</div>
            <button type="button" className="or-btn or-btn--primary or-btn--icon" aria-label="Send" title="Send" disabled>
              <Icon name="arrowUp" />
            </button>
          </div>
        ) : (
          <div className="or-composer">
            <textarea
              ref={box}
              rows={1}
              placeholder="Ask about this book"
              aria-label="Ask about this book"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button
              type="button"
              className="or-btn or-btn--primary or-btn--icon"
              aria-label="Send"
              title="Send"
              disabled={!draft.trim() || pending}
              onClick={send}
            >
              <Icon name="arrowUp" />
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

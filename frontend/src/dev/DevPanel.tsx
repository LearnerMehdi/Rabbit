import { useState } from "react";
import { mockApi } from "../api";
import { setSettings, type ChatMode } from "../api/settings";
import { Icon } from "../components/Icon";
import { useMockSettings } from "../lib/hooks";

/**
 * Controls for the mock backend. Not part of the product UI: it exists so the
 * frontend can be exercised end to end before the real endpoints are connected.
 */
export function DevPanel() {
  const s = useMockSettings();
  const [open, setOpen] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  if (!open) {
    return (
      <button type="button" className="or app-dev__toggle or-annot" onClick={() => setOpen(true)} title="Mock backend settings">
        mock backend
      </button>
    );
  }

  return (
    <div className="or app-dev" role="dialog" aria-label="Mock backend">
      <div className="app-dev__head">
        <span className="or-label">Mock backend</span>
        <button type="button" className="or-btn or-btn--ghost or-btn--icon" aria-label="Close" onClick={() => setOpen(false)}>
          <Icon name="close" />
        </button>
      </div>
      <p className="or-cap">No backend is connected. Books are kept in this browser; preparation and chat are simulated.</p>

      <label className="or-field">
        <span className="or-label">Chat</span>
        <select
          className="or-input"
          value={s.chatMode}
          onChange={(e) => setSettings({ chatMode: e.target.value as ChatMode })}
        >
          <option value="unavailable">Unavailable (default)</option>
          <option value="echo">Answers with a mock reply</option>
          <option value="error">Every answer fails</option>
        </select>
      </label>

      <label className="or-field">
        <span className="or-label">Preparation speed</span>
        <select className="or-input" value={s.speed} onChange={(e) => setSettings({ speed: Number(e.target.value) })}>
          <option value={0.25}>0.25× (slow)</option>
          <option value={1}>1× (like the backend, ~16 pages/s)</option>
          <option value={5}>5×</option>
          <option value={25}>25× (near instant)</option>
        </select>
      </label>

      <label className="or-field">
        <span className="or-label">Latency per call</span>
        <select className="or-input" value={s.latencyMs} onChange={(e) => setSettings({ latencyMs: Number(e.target.value) })}>
          <option value={0}>None</option>
          <option value={150}>150 ms</option>
          <option value={800}>800 ms</option>
          <option value={2000}>2 s</option>
        </select>
      </label>

      <label className="app-dev__check">
        <input type="checkbox" checked={s.failNext} onChange={(e) => setSettings({ failNext: e.target.checked })} />
        <span>Fail the next preparation</span>
      </label>

      <button
        type="button"
        className={`or-btn ${confirmClear ? "or-btn--danger" : "or-btn--secondary"}`}
        onBlur={() => setConfirmClear(false)}
        onClick={() => {
          if (!confirmClear) return setConfirmClear(true);
          setConfirmClear(false);
          void mockApi.reset();
        }}
      >
        <Icon name="trash" />
        {confirmClear ? "Click again to remove every book" : "Clear mock library"}
      </button>
    </div>
  );
}

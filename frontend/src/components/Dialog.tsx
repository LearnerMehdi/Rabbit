import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

/**
 * Modal over the overlay scrim. Focus goes to `initialFocus` (Cancel by
 * convention, never Delete), is trapped inside, Esc and a scrim click cancel,
 * and focus returns to the trigger on close.
 */
export function Dialog({
  title,
  wide,
  onClose,
  children,
  footer,
  initialFocus,
}: {
  title: string;
  wide?: boolean;
  onClose: () => void;
  children: React.ReactNode;
  footer: React.ReactNode;
  initialFocus?: React.RefObject<HTMLElement>;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    (initialFocus?.current ?? ref.current?.querySelector<HTMLElement>(FOCUSABLE))?.focus();
    return () => trigger?.focus?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
    } else if (e.key === "Tab" && ref.current) {
      const items = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };

  return createPortal(
    <div className="or app-scrim" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <div
        className="or-scrim app-scrim__inner"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
      >
        <div
          ref={ref}
          className={`or-dialog${wide ? " or-dialog--wide" : ""}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onKeyDown={onKeyDown}
        >
          <div className="or-dialog__head">
            <h2 className="or-dialog__title" id={titleId}>
              {title}
            </h2>
          </div>
          <div className="or-dialog__body">{children}</div>
          <div className="or-dialog__foot">{footer}</div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

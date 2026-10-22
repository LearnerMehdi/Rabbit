import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon, type IconName } from "./Icon";

export interface MenuItem {
  label: string;
  icon?: IconName;
  danger?: boolean;
  selected?: boolean;
  separatorBefore?: boolean;
  onSelect: () => void;
}

/**
 * Floating command list anchored to `anchor`. Arrow keys move, Enter chooses,
 * Esc or an outside click closes and returns focus to the trigger.
 */
export function Menu({
  anchor,
  items,
  onClose,
  align = "right",
  radio,
}: {
  anchor: HTMLElement;
  items: MenuItem[];
  onClose: () => void;
  align?: "left" | "right";
  radio?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    const r = anchor.getBoundingClientRect();
    const w = ref.current?.offsetWidth ?? 168;
    const h = ref.current?.offsetHeight ?? 0;
    let top = r.bottom + 4;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 4);
    const left = align === "right" ? Math.max(8, r.right - w) : Math.min(r.left, window.innerWidth - w - 8);
    setPos({ top, left });
  }, [anchor, align]);

  useEffect(() => {
    const first = ref.current?.querySelector<HTMLElement>(radio ? ".is-selected" : ".or-menu__item");
    (first ?? ref.current?.querySelector<HTMLElement>(".or-menu__item"))?.focus();
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node) && !anchor.contains(e.target as Node)) onClose();
    };
    const onScroll = () => onClose();
    document.addEventListener("mousedown", onDown);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("resize", onScroll);
    };
  }, [anchor, onClose, radio]);

  const close = () => {
    onClose();
    anchor.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    const rows = [...(ref.current?.querySelectorAll<HTMLElement>(".or-menu__item") ?? [])];
    const i = rows.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      rows[(i + 1) % rows.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      rows[(i - 1 + rows.length) % rows.length]?.focus();
    } else if (e.key === "Escape" || e.key === "Tab") {
      e.preventDefault();
      close();
    }
  };

  return createPortal(
    <div
      ref={ref}
      className="or or-menu app-menu"
      role="menu"
      style={pos ? { top: pos.top, left: pos.left } : { visibility: "hidden" }}
      // React bubbles portal events through the component tree: keep them out of the card
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation();
        onKeyDown(e);
      }}
    >
      {items.map((item) => (
        <div key={item.label} style={{ display: "contents" }}>
          {item.separatorBefore && <div className="or-menu__sep" role="separator" />}
          <button
            type="button"
            className={`or-menu__item${item.danger ? " or-menu__item--danger" : ""}${item.selected ? " is-selected" : ""}`}
            role={radio ? "menuitemradio" : "menuitem"}
            aria-checked={radio ? !!item.selected : undefined}
            onClick={() => {
              onClose();
              item.onSelect();
            }}
          >
            {item.icon && <Icon name={item.icon} />}
            {item.label}
            {item.selected && (
              <span className="or-menu__check">
                <Icon name="check" />
              </span>
            )}
          </button>
        </div>
      ))}
    </div>,
    document.body,
  );
}

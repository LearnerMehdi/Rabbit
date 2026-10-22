import type { PDFDocumentProxy } from "pdfjs-dist";
import { useEffect, useRef, useState } from "react";
import { PageCanvas, type PageSize } from "./PdfPages";

const THUMB_W = 104;

/** Collapsible sidebar of page thumbnails; renders only the ones in view. */
export function Thumbnails({
  doc,
  sizes,
  current,
  onSelect,
}: {
  doc: PDFDocumentProxy;
  sizes: PageSize[];
  current: number;
  onSelect: (page: number) => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState<Set<number>>(new Set());

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        setVisible((prev) => {
          const next = new Set(prev);
          for (const e of entries) {
            const p = Number((e.target as HTMLElement).dataset.page);
            if (e.isIntersecting) next.add(p);
            else next.delete(p);
          }
          return next;
        });
      },
      { root: el, rootMargin: "400px 0px" },
    );
    el.querySelectorAll("[data-page]").forEach((n) => io.observe(n));
    return () => io.disconnect();
  }, [sizes.length]);

  // keep the current page in view
  useEffect(() => {
    root.current?.querySelector(`[data-page="${current}"]`)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  return (
    <nav ref={root} className="or-thumbs app-thumbs" aria-label="Pages">
      {sizes.map((s, i) => {
        const page = i + 1;
        const active = page === current;
        const scale = THUMB_W / s.w;
        return (
          <button
            key={page}
            type="button"
            data-page={page}
            className={`or-thumb${active ? " is-active" : ""}`}
            aria-current={active ? "page" : undefined}
            aria-label={`Page ${page}`}
            onClick={() => onSelect(page)}
          >
            <div className="or-page app-thumb__page" style={{ width: THUMB_W, height: Math.round(s.h * scale) }}>
              {visible.has(page) && <PageCanvas doc={doc} page={page} scale={scale} visible className="app-page__canvas" />}
            </div>
            <span className="or-thumb__num">{page}</span>
          </button>
        );
      })}
    </nav>
  );
}

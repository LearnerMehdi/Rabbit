/** pdf.js helpers: everything the UI does with PDFs runs in the browser. */
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PdfFacts } from "../api/mock";

let lib: Promise<typeof import("pdfjs-dist")> | null = null;

export function pdfjs() {
  lib ??= (async () => {
    const mod = await import("pdfjs-dist");
    const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
    mod.GlobalWorkerOptions.workerSrc = worker.default;
    return mod;
  })();
  return lib;
}

export async function loadPdf(file: Blob): Promise<PDFDocumentProxy> {
  const { getDocument } = await pdfjs();
  // pdf.js takes ownership of (detaches) the buffer it is given
  const data = new Uint8Array(await file.arrayBuffer());
  return getDocument({ data }).promise;
}

export interface PdfPreview extends PdfFacts {
  title: string | null;
  author: string | null;
}

/** Page count, metadata, cover and a text-layer check, for the Add book dialog and the mock. */
export async function inspectPdf(file: Blob): Promise<PdfPreview> {
  let doc: PDFDocumentProxy;
  try {
    doc = await loadPdf(file);
  } catch (e) {
    if ((e as { name?: string }).name === "PasswordException") {
      return { pageCount: 0, encrypted: true, needsOcr: false, cover: null, title: null, author: null };
    }
    throw e;
  }
  try {
    const meta = (await doc.getMetadata().catch(() => null))?.info as Record<string, unknown> | undefined;
    const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : null);

    // sample up to 12 pages spread over the book
    const n = doc.numPages;
    const sample = [...new Set(Array.from({ length: Math.min(12, n) }, (_, i) => 1 + Math.floor((i * n) / Math.min(12, n))))];
    let empty = 0;
    for (const p of sample) {
      const text = await (await doc.getPage(p)).getTextContent();
      if (!text.items.some((it) => "str" in it && it.str.trim())) empty++;
    }

    return {
      pageCount: n,
      encrypted: false,
      needsOcr: empty / sample.length > 0.8,
      cover: await renderCover(doc),
      title: str(meta?.Title),
      author: str(meta?.Author),
    };
  } finally {
    void doc.destroy();
  }
}

async function renderCover(doc: PDFDocumentProxy, width = 272): Promise<string | null> {
  try {
    const page = await doc.getPage(1);
    const base = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: width / base.width });
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(viewport.width);
    canvas.height = Math.round(viewport.height);
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    await page.render({ canvasContext: ctx, viewport }).promise;
    return canvas.toDataURL("image/jpeg", 0.85);
  } catch {
    return null;
  }
}

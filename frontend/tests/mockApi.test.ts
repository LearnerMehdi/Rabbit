// @vitest-environment node
import { beforeEach, describe, expect, it } from "vitest";
import { CHAT_UNAVAILABLE, MockApi, type PdfFacts } from "../src/api/mock";
import { setSettings } from "../src/api/settings";
import { ApiError, type Book } from "../src/api/types";

const pdf = (body: string, name = "book.pdf") => new File([`%PDF-1.7\n${body}`], name, { type: "application/pdf" });

function facts(over: Partial<PdfFacts> = {}): PdfFacts {
  return { pageCount: 10, encrypted: false, needsOcr: false, cover: null, ...over };
}

let n = 0;
function makeApi(f: (file: Blob) => PdfFacts = () => facts()) {
  return new MockApi(async (file) => f(file), { dbName: `test-${n++}` });
}

function waitFor(api: MockApi, id: string, status: Book["status"], timeout = 5000): Promise<Book> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`timed out waiting for ${status}`)), timeout);
    const check = async () => {
      const b = (await api.listBooks()).find((x) => x.id === id);
      if (b?.status === status) {
        clearTimeout(t);
        off();
        resolve(b);
      }
    };
    const off = api.onLibraryChange(() => void check());
    void check();
  });
}

beforeEach(() => setSettings({ speed: 25, latencyMs: 0, failNext: false, chatMode: "unavailable" }));

describe("MockApi", () => {
  it("adds a book that goes through the backend's stages to ready", async () => {
    setSettings({ speed: 1 }); // at high speed one tick jumps straight to 100%
    const api = makeApi();
    const book = await api.addBook(pdf("a"), { title: "  Deep Learning ", author: "" });
    expect(book).toMatchObject({ title: "Deep Learning", author: null, status: "indexing", percent: 0 });

    const stages = new Set<string>();
    const percents: number[] = [];
    api.onBookProgress(book.id, (p) => {
      if (p.stage) stages.add(p.stage);
      percents.push(p.percent);
    });
    const ready = await waitFor(api, book.id, "ready");
    expect(ready).toMatchObject({ percent: 100, pageCount: 10, error: null });
    expect([...stages]).toEqual(expect.arrayContaining(["chunking", "embedding", "saving"]));
    expect(percents).toEqual([...percents].sort((a, b) => a - b));
  });

  it("rejects files that aren't PDFs and duplicates", async () => {
    const api = makeApi();
    await expect(api.addBook(new File(["hello"], "notes.pdf"), { title: "x" })).rejects.toMatchObject({ code: "not_pdf" });
    await api.addBook(pdf("same"), { title: "One" });
    await expect(api.addBook(pdf("same", "copy.pdf"), { title: "Two" })).rejects.toMatchObject({
      code: "duplicate",
      message: "This book is already in your library.",
    });
    expect(await api.listBooks()).toHaveLength(1);
  });

  it("fails scanned and encrypted PDFs with the backend's messages", async () => {
    const api = makeApi((file) => facts((file as File).name === "scan.pdf" ? { needsOcr: true } : { encrypted: true }));
    const scan = await api.addBook(pdf("s", "scan.pdf"), { title: "Scan" });
    const enc = await api.addBook(pdf("e", "enc.pdf"), { title: "Enc" });
    expect((await waitFor(api, scan.id, "failed")).error).toBe("No text layer (scanned PDF)");
    expect((await waitFor(api, enc.id, "failed")).error).toBe("PDF is password-protected");
  });

  it("failNext fails exactly one preparation, and reindex recovers it", async () => {
    const api = makeApi();
    setSettings({ failNext: true });
    const a = await api.addBook(pdf("a"), { title: "A" });
    await waitFor(api, a.id, "failed");
    const b = await api.addBook(pdf("b"), { title: "B" });
    await waitFor(api, b.id, "ready");
    await api.reindexBook(a.id);
    expect((await api.listBooks()).find((x) => x.id === a.id)).toMatchObject({ status: "indexing", percent: 0 });
    await waitFor(api, a.id, "ready");
  });

  it("lists with search and the three sorts", async () => {
    const api = makeApi();
    const b1 = await api.addBook(pdf("1"), { title: "Bishop PRML", author: "Christopher Bishop" });
    await new Promise((r) => setTimeout(r, 5));
    const b2 = await api.addBook(pdf("2"), { title: "Algorithms" });
    expect((await api.listBooks({ sort: "added" })).map((b) => b.id)).toEqual([b2.id, b1.id]); // new first
    expect((await api.listBooks({ sort: "title" })).map((b) => b.title)).toEqual(["Algorithms", "Bishop PRML"]);
    await api.openBook(b1.id);
    expect((await api.listBooks({ sort: "opened" }))[0].id).toBe(b1.id);
    expect((await api.listBooks({ query: "christopher" })).map((b) => b.id)).toEqual([b1.id]);
  });

  it("renames, saves the last page, opens and deletes", async () => {
    const api = makeApi();
    const b = await api.addBook(pdf("x"), { title: "Old" });
    expect((await api.updateBook(b.id, { title: "New" })).title).toBe("New");
    await api.saveLastPage(b.id, 7);
    const opened = await api.openBook(b.id);
    expect(opened.book).toMatchObject({ title: "New", lastPage: 7 });
    expect(await opened.file.text()).toContain("%PDF");
    await api.deleteBook(b.id);
    expect(await api.listBooks()).toEqual([]);
    await expect(api.openBook(b.id)).rejects.toBeInstanceOf(ApiError);
  });

  it("deleting while preparing stops the job", async () => {
    const api = makeApi(() => facts({ pageCount: 500 }));
    setSettings({ speed: 1 });
    const b = await api.addBook(pdf("big"), { title: "Big" });
    await api.deleteBook(b.id);
    await new Promise((r) => setTimeout(r, 600));
    expect(await api.listBooks()).toEqual([]);
  });

  it("chat is unavailable by default; other modes answer or fail", async () => {
    const api = makeApi();
    const b = await api.addBook(pdf("c"), { title: "Chat" });
    await expect(api.askQuestion(b.id, "too early?")).rejects.toMatchObject({ code: "not_ready" });
    await waitFor(api, b.id, "ready");

    expect(await api.getChatAvailability()).toBe("unavailable");
    await expect(api.askQuestion(b.id, "hi")).rejects.toMatchObject({ code: "unavailable", message: CHAT_UNAVAILABLE });

    setSettings({ chatMode: "echo" });
    expect(await api.getChatAvailability()).toBe("available");
    expect((await api.askQuestion(b.id, "What is ELBO?")).answer).toContain("What is ELBO?");

    setSettings({ chatMode: "error" });
    await expect(api.askQuestion(b.id, "hi")).rejects.toMatchObject({ code: "failed" });
  });
});

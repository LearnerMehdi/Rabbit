import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HttpApi } from "../src/api/http";
import { ApiError } from "../src/api/types";

/** Minimal EventSource stand-in: tests emit server events by hand. */
class FakeEventSource {
  static last: FakeEventSource | null = null;
  listeners = new Map<string, ((e: MessageEvent | Event) => void)[]>();
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, cb: (e: MessageEvent | Event) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), cb]);
  }
  emit(type: string, data?: unknown) {
    const e = data === undefined ? new Event(type) : new MessageEvent(type, { data: JSON.stringify(data) });
    this.listeners.get(type)?.forEach((cb) => cb(e));
  }
}

const reply = (status: number, body?: unknown, type = "application/json") =>
  new Response(body === undefined ? null : type === "application/json" ? JSON.stringify(body) : (body as BodyInit), {
    status,
    headers: { "Content-Type": type },
  });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("EventSource", FakeEventSource);
  FakeEventSource.last = null;
});
afterEach(() => vi.unstubAllGlobals());

describe("HttpApi", () => {
  it("maps backend errors to ApiError codes and messages", async () => {
    fetchMock.mockResolvedValue(reply(409, { code: "duplicate", message: "This book is already in your library." }));
    const err = await new HttpApi().addBook(new File(["%PDF-1.7"], "a.pdf"), { title: "A" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("duplicate");
    expect(err.message).toBe("This book is already in your library.");
  });

  it("treats unknown error bodies and network failures as 'failed'", async () => {
    fetchMock.mockResolvedValueOnce(reply(500, "oops", "text/plain"));
    expect((await new HttpApi().listBooks().catch((e) => e)).code).toBe("failed");
    fetchMock.mockRejectedValueOnce(new TypeError("network"));
    expect((await new HttpApi().listBooks().catch((e) => e)).code).toBe("failed");
  });

  it("uploads the file with title and author as multipart form data", async () => {
    fetchMock.mockResolvedValue(reply(201, { id: "b1" }));
    await new HttpApi().addBook(new File(["%PDF-1.7"], "book.pdf"), { title: " Title ", author: "Ann" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/books");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect(form.get("title")).toBe("Title");
    expect(form.get("author")).toBe("Ann");
    expect((form.get("file") as File).name).toBe("book.pdf");
  });

  it("sends search and sort as query parameters", async () => {
    fetchMock.mockResolvedValue(reply(200, []));
    await new HttpApi().listBooks({ query: "graph theory", sort: "title" });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/books?query=graph+theory&sort=title");
  });

  it("openBook marks the book opened and returns the PDF as a Blob", async () => {
    fetchMock
      .mockResolvedValueOnce(reply(200, { id: "b1", title: "T" }))
      .mockResolvedValueOnce(reply(200, "%PDF-1.7 bytes", "application/pdf"));
    const { book, file } = await new HttpApi().openBook("b1");
    expect(fetchMock.mock.calls.map((c) => [c[0], c[1]?.method])).toEqual([
      ["/api/books/b1/open", "POST"],
      ["/api/books/b1/file", undefined],
    ]);
    expect(book.title).toBe("T");
    expect(file).toBeInstanceOf(Blob);
    expect(file.size).toBe("%PDF-1.7 bytes".length);
  });

  it("asks one question per request with only the question in the body", async () => {
    fetchMock.mockImplementation(async () => reply(200, { answer: "42" }));
    const api = new HttpApi();
    expect(await api.askQuestion("b1", "first?")).toEqual({ answer: "42" });
    await api.askQuestion("b1", "second?");
    expect(fetchMock.mock.calls.map((c) => JSON.parse(c[1].body))).toEqual([{ question: "first?" }, { question: "second?" }]);
  });

  it("reports chat as unavailable when the backend says so or can't be reached", async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { availability: "available" }));
    expect(await new HttpApi().getChatAvailability()).toBe("available");
    fetchMock.mockRejectedValueOnce(new TypeError("network"));
    expect(await new HttpApi().getChatAvailability()).toBe("unavailable");
  });

  it("dispatches progress events to the listeners of that book only, over one EventSource", () => {
    const api = new HttpApi();
    const a = vi.fn();
    const b = vi.fn();
    api.onBookProgress("a", a);
    const unsubscribeB = api.onBookProgress("b", b);
    const es = FakeEventSource.last!;
    expect(es.url).toBe("/api/events");

    es.emit("progress", { bookId: "a", percent: 42, status: "indexing", stage: "embedding", error: null });
    expect(a).toHaveBeenCalledWith({ percent: 42, status: "indexing", stage: "embedding", error: null });
    expect(b).not.toHaveBeenCalled();

    unsubscribeB();
    es.emit("progress", { bookId: "b", percent: 100, status: "ready", stage: null, error: null });
    expect(b).not.toHaveBeenCalled();

    api.onLibraryChange(() => {});
    expect(FakeEventSource.last).toBe(es);
  });

  it("notifies library listeners on library events and after a reconnect", () => {
    const api = new HttpApi();
    const cb = vi.fn();
    api.onLibraryChange(cb);
    const es = FakeEventSource.last!;
    es.emit("open");
    expect(cb).not.toHaveBeenCalled(); // first connection
    es.emit("library", {});
    es.emit("open"); // reconnected after the server restarted
    expect(cb).toHaveBeenCalledTimes(2);
  });
});

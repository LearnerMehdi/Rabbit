/** Minimal promise wrapper over IndexedDB: two stores, books and files. */

const DB_NAME = "orange-reader-mock";
const VERSION = 1;

export type StoreName = "books" | "files";

function req<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

export class Idb {
  private db: Promise<IDBDatabase>;

  constructor(name = DB_NAME) {
    this.db = new Promise((resolve, reject) => {
      const open = indexedDB.open(name, VERSION);
      open.onupgradeneeded = () => {
        open.result.createObjectStore("books", { keyPath: "id" });
        open.result.createObjectStore("files");
      };
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
    });
  }

  private async store(name: StoreName, mode: IDBTransactionMode) {
    return (await this.db).transaction(name, mode).objectStore(name);
  }

  async get<T>(name: StoreName, key: string): Promise<T | undefined> {
    return req((await this.store(name, "readonly")).get(key));
  }

  async all<T>(name: StoreName): Promise<T[]> {
    return req((await this.store(name, "readonly")).getAll());
  }

  async put(name: StoreName, value: unknown, key?: string): Promise<void> {
    await req((await this.store(name, "readwrite")).put(value, key));
  }

  async delete(name: StoreName, key: string): Promise<void> {
    await req((await this.store(name, "readwrite")).delete(key));
  }

  async clear(): Promise<void> {
    await req((await this.store("books", "readwrite")).clear());
    await req((await this.store("files", "readwrite")).clear());
  }
}

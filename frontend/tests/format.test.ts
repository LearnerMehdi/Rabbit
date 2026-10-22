import { describe, expect, it } from "vitest";
import { formatSize, titleFromFileName, truncate } from "../src/lib/format";

describe("format", () => {
  it("sizes", () => {
    expect(formatSize(500)).toBe("500 B");
    expect(formatSize(19_293_798)).toBe("18.4 MB");
  });
  it("truncates long dialog titles with an ellipsis", () => {
    const t = truncate("x".repeat(80));
    expect(t).toHaveLength(60);
    expect(t.endsWith("…")).toBe(true);
    expect(truncate("Deep Learning")).toBe("Deep Learning");
  });
  it("titles from file names", () => {
    expect(titleFromFileName("bishop_prml_2006.pdf")).toBe("bishop prml 2006");
  });
});

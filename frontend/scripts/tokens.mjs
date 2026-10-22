// Generates src/styles/tokens.css from design/tokens.json (the Orange Reader design system).
import { readFileSync, writeFileSync } from "node:fs";

const t = JSON.parse(readFileSync(new URL("../design/tokens.json", import.meta.url)));
const lines = [];
const resolve = (v) => (typeof v === "string" ? v.replace(/^\{(.+)\}$/, "var(--$1)") : v);
const first = t.color.themes[0].id;

for (const tok of t.color.tokens) {
  const v = typeof tok.value === "object" ? tok.value[first] : tok.value;
  lines.push(`  --${tok.name}: ${resolve(v)};`);
}
for (const [name, stack] of Object.entries(t.type.families)) lines.push(`  --font-${name}: ${stack};`);
for (const fam of ["spacing", "radius", "shadow", "layout"]) {
  for (const tok of t[fam]?.tokens ?? []) lines.push(`  --${tok.name}: ${tok.value};`);
}

const out = `/* ${t.name} — generated from design/tokens.json by scripts/tokens.mjs; do not edit */\n:root {\n${lines.join("\n")}\n}\n`;
writeFileSync(new URL("../src/styles/tokens.css", import.meta.url), out);
console.log(`tokens.css: ${lines.length} variables`);

// Build step: embed every label with the CLIP text encoder and write
// public/labels.json. Run with `npm run embed`.
import { AutoTokenizer, CLIPTextModelWithProjection } from "@huggingface/transformers";
import { writeFile } from "node:fs/promises";
import { OUTDOOR, INDOOR, QUESTS } from "./labels.mjs";

const MODEL = "Xenova/clip-vit-base-patch32";
const tokenizer = await AutoTokenizer.from_pretrained(MODEL);
const textModel = await CLIPTextModelWithProjection.from_pretrained(MODEL, { dtype: "fp32" });

const all = [...OUTDOOR, ...INDOOR, ...QUESTS.map((q) => q.label)];
const inputs = tokenizer(all, { padding: true, truncation: true });
const { text_embeds } = await textModel(inputs);
const [n, d] = text_embeds.dims;
const data = text_embeds.data;

const vectors = {};
for (let i = 0; i < n; i++) {
  const v = Array.from(data.slice(i * d, (i + 1) * d));
  const norm = Math.hypot(...v);
  vectors[all[i]] = v.map((x) => +(x / norm).toFixed(5));
}

await writeFile(
  new URL("../public/labels.json", import.meta.url),
  JSON.stringify({ model: MODEL, dim: d, outdoor: OUTDOOR, indoor: INDOOR, quests: QUESTS, vectors })
);
console.log(`wrote ${n} label embeddings (${d} dims) to public/labels.json`);

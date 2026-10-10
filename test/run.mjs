// Runs the same vision model the browser uses against test/images and
// prints the verdicts. `npm test`
import { AutoProcessor, CLIPVisionModelWithProjection, RawImage } from "@huggingface/transformers";
import { readFile, readdir } from "node:fs/promises";
import { grassCheck, questCheck, normalize } from "../public/core.js";

const table = JSON.parse(await readFile(new URL("../public/labels.json", import.meta.url)));
const processor = await AutoProcessor.from_pretrained(table.model);
const vision = await CLIPVisionModelWithProjection.from_pretrained(table.model, { dtype: process.env.DTYPE || "q8" });

const expectations = {
  "grass.jpg": { outside: true },
  "trail.jpg": { outside: true },
  "redleaf.jpg": { outside: true, quest: "red-leaf" },
  "acorn.jpg": { outside: true, quest: "acorn" },
  "squirrel.jpg": { outside: true, quest: "squirrel" },
  "bird.jpg": { outside: true, quest: "bird" },
  "pumpkin.jpg": { outside: true, quest: "pumpkin" },
  "laptop.jpg": { outside: false, quest: "red-leaf" },
  "office.jpg": { outside: false, quest: "moss" },
  "moss.jpg": { outside: true, quest: "moss" },
  "concert.jpg": { outside: false, quest: "moss" },
  "mushroom2.jpg": { outside: true, quest: "mushroom" },
  "mushroom3.jpg": { outside: true, quest: "mushroom" },
  "cheat-wallpaper.jpg": { outside: false, quest: "bark" },
  "monitor.jpg": { outside: false, quest: "flower" },
};

let fails = 0;
const dir = new URL("./images/", import.meta.url);
for (const f of (await readdir(dir)).sort()) {
  const img = await RawImage.read(new URL(f, dir).pathname);
  const inputs = await processor(img);
  const { image_embeds } = await vision(inputs);
  const vec = normalize(image_embeds.data);
  const g = grassCheck(vec, table);
  const exp = expectations[f];
  let line = `${f.padEnd(14)} outside=${g.outside} (${g.outdoorP.toFixed(2)}) top="${g.top.label}"`;
  if (exp && exp.outside !== g.outside) { fails++; line += "  <-- MISMATCH outside"; }
  if (exp?.quest) {
    const q = questCheck(vec, table, exp.quest);
    const want = exp.outside; // indoor photos should fail their quest
    line += `\n${"".padEnd(14)} quest ${exp.quest}: passed=${q.passed} p=${q.questP.toFixed(2)} screen=${q.screenP.toFixed(2)} top="${q.top.label}"`;
    if (q.passed !== want) { fails++; line += "  <-- MISMATCH quest"; }
  }
  console.log(line);
}
console.log(fails ? `\n${fails} mismatches` : "\nall expectations met");
process.exit(fails ? 1 : 0);

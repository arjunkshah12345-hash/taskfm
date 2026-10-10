// Pure scoring logic shared by the browser app and the Node tests.
// Input: a unit-length CLIP image embedding and the precomputed label table.

const LOGIT_SCALE = 100; // CLIP ViT-B/32's learned temperature

function dot(a, b) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}

export function normalize(v) {
  let n = 0;
  for (const x of v) n += x * x;
  n = Math.sqrt(n) || 1;
  return Array.from(v, (x) => x / n);
}

// Softmax over a set of labels. Returns [{label, p}] sorted high to low.
export function rank(imageVec, labels, vectors) {
  const logits = labels.map((l) => LOGIT_SCALE * dot(imageVec, vectors[l]));
  const max = Math.max(...logits);
  const exps = logits.map((x) => Math.exp(x - max));
  const sum = exps.reduce((a, b) => a + b, 0);
  return labels
    .map((label, i) => ({ label, p: exps[i] / sum }))
    .sort((a, b) => b.p - a.p);
}

// Is this photo outside? Compares outdoor scenes against screens and rooms.
export function grassCheck(imageVec, table) {
  const ranked = rank(imageVec, [...table.outdoor, ...table.indoor], table.vectors);
  const outdoorSet = new Set(table.outdoor);
  const outdoorP = ranked.filter((r) => outdoorSet.has(r.label)).reduce((a, r) => a + r.p, 0);
  return { outside: outdoorP >= 0.6, outdoorP, top: ranked[0] };
}

// Did the photo complete the quest? The quest label has to beat every other
// quest and every indoor label, and the scene must not read as a screen.
export function questCheck(imageVec, table, questId) {
  const quest = table.quests.find((q) => q.id === questId);
  if (!quest) throw new Error(`unknown quest ${questId}`);
  const labels = [...table.quests.map((q) => q.label), ...table.indoor];
  const ranked = rank(imageVec, labels, table.vectors);
  const questP = ranked.find((r) => r.label === quest.label).p;
  const screenP = ranked
    .filter((r) => table.indoor.includes(r.label))
    .reduce((a, r) => a + r.p, 0);
  const passed = ranked[0].label === quest.label && questP >= 0.35 && screenP < 0.3;
  return { passed, questP, screenP, top: ranked[0], quest };
}

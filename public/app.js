import {
  env,
  AutoProcessor,
  CLIPVisionModelWithProjection,
  RawImage,
} from "https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.1/dist/transformers.min.js";
import { grassCheck, questCheck, normalize } from "./core.js";

env.allowLocalModels = false; // weights come from the Hugging Face Hub, then live in the browser cache

const $ = (id) => document.getElementById(id);
const openedAt = Date.now();
const JOURNAL_KEY = "grasscheck.journal.v1";
const QUEST_KEY = "grasscheck.quest.v1";

let table, processor, vision;

// ---------- quests ----------
function todayKey(d = new Date()) {
  return d.toLocaleDateString("en-CA"); // YYYY-MM-DD in local time
}
function questForToday() {
  const saved = JSON.parse(localStorage.getItem(QUEST_KEY) || "null");
  if (saved && saved.day === todayKey()) return saved.id;
  // Same quest for everyone on the same day, so a run club can share one.
  const day = todayKey();
  let h = 0;
  for (const c of day) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return table.quests[h % table.quests.length].id;
}
function setQuest(id) {
  localStorage.setItem(QUEST_KEY, JSON.stringify({ day: todayKey(), id }));
  $("quest-title").textContent = table.quests.find((q) => q.id === id).title;
}
function currentQuestId() {
  return JSON.parse(localStorage.getItem(QUEST_KEY)).id;
}

// ---------- journal ----------
function loadJournal() {
  return JSON.parse(localStorage.getItem(JOURNAL_KEY) || "[]");
}
function saveJournal(entries) {
  localStorage.setItem(JOURNAL_KEY, JSON.stringify(entries.slice(0, 200)));
}
function streak(entries) {
  const days = new Set(entries.filter((e) => e.outside).map((e) => e.day));
  let n = 0;
  const d = new Date();
  if (!days.has(todayKey(d))) d.setDate(d.getDate() - 1); // today still counts until midnight
  while (days.has(todayKey(d))) {
    n++;
    d.setDate(d.getDate() - 1);
  }
  return n;
}
function renderJournal() {
  const entries = loadJournal();
  $("streak").textContent = streak(entries);
  $("empty").hidden = entries.length > 0;
  const list = $("journal");
  list.replaceChildren(
    ...entries.slice(0, 30).map((e) => {
      const li = document.createElement("li");
      const img = document.createElement("img");
      img.src = e.thumb;
      img.alt = "";
      const text = document.createElement("div");
      const status = e.questPassed ? `Quest done: ${e.questTitle}` : e.outside ? "Outside" : "Not outside";
      text.innerHTML = `<strong></strong><small></small>`;
      text.querySelector("strong").textContent = status;
      text.querySelector("small").textContent = `${new Date(e.at).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })} · looked like ${e.top.replace(/^a (close-up )?photo of /, "")}`;
      li.append(img, text);
      return li;
    })
  );
}

// ---------- model ----------
async function loadModel() {
  table = await (await fetch("labels.json")).json();
  setQuest(questForToday());
  renderJournal();

  const files = new Map();
  const progress_callback = (p) => {
    if (p.status === "progress" && p.total) {
      files.set(p.file, p);
      let loaded = 0, total = 0;
      for (const f of files.values()) { loaded += f.loaded; total += f.total; }
      document.querySelector(".progress").hidden = false;
      $("bar").style.width = `${Math.round((100 * loaded) / total)}%`;
      $("model-status").textContent = `Downloading the vision model, ${(loaded / 1e6).toFixed(0)} of ${(total / 1e6).toFixed(0)} MB. This happens once.`;
    }
  };
  processor = await AutoProcessor.from_pretrained(table.model, { progress_callback });
  vision = await CLIPVisionModelWithProjection.from_pretrained(table.model, { dtype: "q8", progress_callback });
  document.querySelector(".progress").hidden = true;
  $("model-status").textContent = navigator.onLine
    ? "Model ready. It is cached now, so this also works with no signal."
    : "Model ready, offline.";
  $("shoot-label").classList.remove("disabled");
}

async function embed(blob) {
  const image = await RawImage.fromBlob(blob);
  const inputs = await processor(image);
  const { image_embeds } = await vision(inputs);
  return normalize(image_embeds.data);
}

async function thumbnail(blob) {
  const bmp = await createImageBitmap(blob);
  const s = 160, c = document.createElement("canvas");
  c.width = c.height = s;
  const k = Math.max(s / bmp.width, s / bmp.height);
  const w = bmp.width * k, h = bmp.height * k;
  c.getContext("2d").drawImage(bmp, (s - w) / 2, (s - h) / 2, w, h);
  return c.toDataURL("image/jpeg", 0.7);
}

const pct = (p) => `${Math.round(p * 100)}%`;
const plain = (label) => label.replace(/^a (close-up )?photo of /, "");

async function onPhoto(file) {
  if (!file) return;
  $("shoot-text").textContent = "Looking";
  const [vec, thumb] = await Promise.all([embed(file), thumbnail(file)]);
  const g = grassCheck(vec, table);
  const q = questCheck(vec, table, currentQuestId());

  $("result").hidden = false;
  $("preview").src = thumb;
  const v = $("verdict");
  if (q.passed) {
    v.textContent = `Quest done: ${q.quest.title.toLowerCase()}`;
    v.className = "pass";
  } else if (g.outside) {
    v.textContent = "You touched grass";
    v.className = "pass";
  } else {
    v.textContent = "That looks like inside";
    v.className = "fail";
  }
  $("detail").textContent = q.passed
    ? `The model is ${pct(q.questP)} sure this is ${plain(q.quest.label)}.`
    : g.outside
      ? `Outside, ${pct(g.outdoorP)} sure. Closest match: ${plain(g.top.label)}. The quest is still open.`
      : `Closest match: ${plain(g.top.label)}. Screens and rooms do not count. Nice try.`;
  const secs = Math.round((Date.now() - openedAt) / 1000);
  $("put-away").textContent = g.outside || q.passed
    ? `You have been on this screen for ${secs} seconds. That is enough. Put the phone away.`
    : "";

  const entries = loadJournal();
  entries.unshift({
    at: Date.now(),
    day: todayKey(),
    outside: g.outside || q.passed,
    questPassed: q.passed,
    questTitle: q.quest.title,
    top: (q.passed ? q.top : g.top).label,
    thumb,
  });
  saveJournal(entries);
  renderJournal();
  $("shoot-text").textContent = "Take another photo";
}

// ---------- wire up ----------
$("shoot-label").classList.add("disabled");
$("photo").addEventListener("change", (e) => {
  const file = e.target.files[0];
  e.target.value = ""; // so picking the same photo again still fires "change"
  onPhoto(file).catch(showError);
});
$("shuffle").addEventListener("click", () => {
  const others = table.quests.filter((x) => x.id !== currentQuestId());
  setQuest(others[Math.floor(Math.random() * others.length)].id);
});
function showError(err) {
  console.error(err);
  $("model-status").textContent = `Something went wrong: ${err.message}`;
  $("shoot-text").textContent = "Take a photo outside";
}
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
loadModel().catch(showError);

// For automated tests: run a photo through the same path the file picker uses.
window.__grasscheck = { onPhoto, setQuest, ready: () => !!vision };

// End-to-end check in real Chrome: load the page, wait for the model, feed it
// photos through the file input, then reload offline. `npm run test:browser`
import puppeteer from "puppeteer-core";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";

const root = new URL("../public/", import.meta.url).pathname;
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".webmanifest": "application/manifest+json" };
const server = createServer(async (req, res) => {
  const path = join(root, decodeURIComponent(new URL(req.url, "http://x").pathname).replace(/\/$/, "/index.html"));
  try { res.writeHead(200, { "content-type": types[extname(path)] || "application/octet-stream" }); res.end(await readFile(path)); }
  catch { res.writeHead(404); res.end(); }
}).listen(4173);

const browser = await puppeteer.launch({ executablePath: process.env.CHROME || "/usr/bin/google-chrome", headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage();
page.on("console", (m) => m.type() === "error" && console.log("console:", m.text()));
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto("http://localhost:4173/", { waitUntil: "load" });
await page.waitForFunction(() => window.__grasscheck?.ready(), { timeout: 240000 });
console.log("model ready:", await page.$eval("#model-status", (e) => e.textContent));

const shots = ["trail.jpg", "laptop.jpg", "cheat-wallpaper.jpg", "redleaf.jpg"];
const input = await page.$("#photo");
for (const s of shots) {
  await page.evaluate(() => { document.getElementById("verdict").textContent = ""; });
  await input.uploadFile(new URL(`./images/${s}`, import.meta.url).pathname);
  await page.waitForFunction(() => document.getElementById("verdict").textContent !== "", { timeout: 60000 });
  const v = await page.$eval("#verdict", (e) => e.textContent);
  const d = await page.$eval("#detail", (e) => e.textContent);
  console.log(`${s.padEnd(20)} ${v} | ${d}`);
}
// Quest path: pin today's quest to "red-leaf" and send the leaf photo.
await page.evaluate(() => window.__grasscheck.setQuest("red-leaf"));
await page.evaluate(() => { document.getElementById("verdict").textContent = ""; });
await input.uploadFile(new URL("./images/redleaf.jpg", import.meta.url).pathname);
await page.waitForFunction(() => document.getElementById("verdict").textContent !== "", { timeout: 60000 });
console.log(`quest red-leaf       ${await page.$eval("#verdict", (e) => e.textContent)} | ${await page.$eval("#detail", (e) => e.textContent)}`);
console.log("quest:", await page.$eval("#quest-title", (e) => e.textContent), "| streak:", await page.$eval("#streak", (e) => e.textContent));
await page.screenshot({ path: new URL("./images/screenshot.png", import.meta.url).pathname, fullPage: true });

// Offline: reload with the network cut and make sure the model still loads.
await page.setOfflineMode(true);
await page.reload({ waitUntil: "load" });
await page.waitForFunction(() => window.__grasscheck?.ready(), { timeout: 120000 });
console.log("offline reload:", await page.$eval("#model-status", (e) => e.textContent));
await browser.close();
server.close();

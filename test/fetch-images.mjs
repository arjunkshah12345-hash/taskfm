// Downloads the test photos from Wikimedia Commons (they are not committed)
// and builds the "nature wallpaper on a monitor" cheat photo with sharp.
import { mkdir, access, writeFile } from "node:fs/promises";
import sharp from "sharp";

const dir = new URL("./images/", import.meta.url);
await mkdir(dir, { recursive: true });
const UA = { "user-agent": "grasscheck-tests/1.0 (https://github.com/arjunkshah12345-hash/grasscheck)" };

// file name -> Commons file title
const PHOTOS = {
  "grass.jpg": "Close up of the lawn mower with grass and flowers in background.jpg",
  "redleaf.jpg": "Red maple leaf on paper birch.jpg",
  "laptop.jpg": "Laptop on desk book stacks (Unsplash).jpg",
  "mushroom.jpg": "Forest floor still life with flowers, mushrooms, butterflies, snake, frog and dragonfly by Snuffelaer.jpg",
  "pumpkin.jpg": "Cucurbita 2011 G1.jpg",
  "office.jpg": "Office desks overview.jpg",
  "trail.jpg": "Hiking trail to Biskupská kupa, Czechia.jpg",
  "acorn.jpg": "Acorns are plentiful in the autumn in the forest at Fort Raleigh National Historic Site. (5db1d10f-1dd8-b71c-0785-a9f0d86bdbe3).jpg",
  "squirrel.jpg": "Leucistic white squirrel hanging on to a tree (85569).jpg",
  "monitor.jpg": "Computer desk.jpg",
  "bird.jpg": "European robin Créteil 2.jpg",
  "kitchen.jpg": "Dirck de Vries - Kitchen Interior - Walters 372651.jpg",
  "mushroom2.jpg": "Mushroom grove scenic brown orange fungus forest d archuleta 2015 (22655640508).jpg",
  "mushroom3.jpg": "Mushroom on a tree trunk.jpg",
  "moss.jpg": "Roof cushion moss Leucobryum in Tottenham, London 01.jpg",
  "concert.jpg": "Moss Poppodium Apollo 2012.jpg",
};

const exists = (u) => access(u).then(() => true, () => false);
for (const [name, title] of Object.entries(PHOTOS)) {
  const out = new URL(name, dir);
  if (await exists(out)) continue;
  const api = `https://commons.wikimedia.org/w/api.php?action=query&titles=${encodeURIComponent("File:" + title)}&prop=imageinfo&iiprop=url&iiurlwidth=640&format=json`;
  const page = Object.values((await (await fetch(api, { headers: UA })).json()).query.pages)[0];
  const img = await fetch(page.imageinfo[0].thumburl, { headers: UA });
  await writeFile(out, Buffer.from(await img.arrayBuffer()));
  console.log("fetched", name);
}

const cheat = new URL("cheat-wallpaper.jpg", dir);
if (!(await exists(cheat))) {
  const screen = await sharp(new URL("trail.jpg", dir).pathname).resize(360, 220).toBuffer();
  const bezel = await sharp({ create: { width: 384, height: 244, channels: 3, background: "#0f0f0f" } })
    .composite([{ input: screen, left: 12, top: 12 }]).png().toBuffer();
  const stand = await sharp({ create: { width: 60, height: 66, channels: 3, background: "#1e1e1e" } }).png().toBuffer();
  await sharp(new URL("office.jpg", dir).pathname).resize(640, 480)
    .composite([{ input: bezel, left: 130, top: 90 }, { input: stand, left: 290, top: 334 }])
    .jpeg({ quality: 90 }).toFile(cheat.pathname);
  console.log("built cheat-wallpaper.jpg");
}

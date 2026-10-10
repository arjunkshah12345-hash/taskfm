# Grass Check

Proof you went outside.

Open the page, look at today's quest (find a red leaf, spot a bird, catch the sunset), take a photo outside, and an open vision model on your own phone decides whether you did it. Then it tells you to put the phone away.

- **Live:** https://arjunkshah12345-hash.github.io/grasscheck/
- **No server.** The photo never leaves the phone. There is no backend, no account, and no analytics.
- **No signal needed.** After the first visit the app, the runtime and the model are cached, so it works on a trail in airplane mode.
- **Hard to fake.** A photo of a nature wallpaper on your monitor reads as a screen, not a forest.

## How it works

| Piece | What it is |
| --- | --- |
| Model | [CLIP ViT-B/32](https://huggingface.co/Xenova/clip-vit-base-patch32), open weights, 8-bit ONNX export of the vision encoder |
| Runtime | [Transformers.js](https://github.com/huggingface/transformers.js) on ONNX Runtime Web (WebAssembly), in the browser tab |
| Labels | 37 short text prompts (outdoor scenes, screens and rooms, 16 fall quests) |
| Storage | `localStorage` for the journal and streak, Cache API for the model |

CLIP has two halves: a text encoder and an image encoder that map into the same space. The label prompts never change, so `npm run embed` runs the text encoder once at build time and writes the vectors to `public/labels.json`. The phone only downloads the image encoder. At check time the app embeds the photo, takes a softmax over its similarity to each label, and applies two rules (`public/core.js`):

- **Outside:** the outdoor labels together hold at least 60% of the probability against screens and rooms.
- **Quest:** the quest's label is the top match among all quests plus the screen and room labels, holds at least 35%, and screens and rooms hold less than 30%.

## Run it

```bash
npm install
npm run serve          # static server for public/
npm test               # model checks against 15 labeled photos (Node)
npm run test:browser   # end to end in headless Chrome, including an offline reload
```

`npm test` downloads the test photos from Wikimedia Commons into `test/images/` (not committed) and builds the wallpaper-on-a-monitor cheat photo with sharp.

## Change the quests

Edit `scripts/labels.mjs`, run `npm run embed`, then `npm test`. The GitHub Pages workflow re-embeds and re-tests on every push to `main`.

## Known limits

- CLIP judges the whole frame. A tight studio-style close-up on a plain background can lose to a similar-looking label (a green acorn on a blurred background read as a flower in testing). Get a bit of the surroundings in the shot.
- It checks that a photo looks like the quest. It does not check where or when you took it.

## Test photos

Test photos come from Wikimedia Commons and are fetched at test time, not shipped. Each file's author and license are on its Commons page; the titles are listed in `test/fetch-images.mjs`.

## License

MIT

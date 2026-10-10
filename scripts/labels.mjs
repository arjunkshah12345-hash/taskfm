// Every label the app can recognize. Text embeddings for these are computed
// once at build time (scripts/embed-labels.mjs), so the phone only downloads
// the CLIP vision encoder.

export const OUTDOOR = [
  "a photo of green grass",
  "a photo of trees outdoors",
  "a photo of a hiking trail",
  "a photo of a garden",
  "a photo of the sky and clouds",
  "a photo of a park",
  "a photo of fallen autumn leaves on the ground",
  "a photo of a beach or a lake shore",
  "a photo of a forest",
  "a photo of a city street outdoors",
  "a close-up photo of a plant, nut, fruit or animal outdoors",
];

export const INDOOR = [
  "a photo of a computer screen",
  "a photo of a laptop on a desk",
  "a photo of a phone screen",
  "a screenshot",
  "a photo of a computer monitor on a desk",
  "a photo of a TV screen",
  "a photo of an indoor room",
  "a photo of an office",
  "a photo of a bedroom",
  "a photo of a kitchen",
];

// Fall quests. `label` is what CLIP compares against; `title` is what the UI shows.
export const QUESTS = [
  { id: "red-leaf", title: "Find a red leaf", label: "a photo of a red autumn leaf" },
  { id: "yellow-leaf", title: "Find a yellow leaf", label: "a photo of a yellow autumn leaf" },
  { id: "acorn", title: "Find an acorn", label: "a photo of an acorn, the nut of an oak tree" },
  { id: "pinecone", title: "Find a pinecone", label: "a photo of a pinecone" },
  { id: "mushroom", title: "Find a mushroom", label: "a photo of a mushroom growing outdoors" },
  { id: "moss", title: "Find some moss", label: "a photo of green moss" },
  { id: "bird", title: "Spot a bird", label: "a photo of a bird" },
  { id: "squirrel", title: "Spot a squirrel", label: "a photo of a squirrel" },
  { id: "pumpkin", title: "Find a pumpkin", label: "a photo of a pumpkin" },
  { id: "flower", title: "Find a flower", label: "a photo of a flower" },
  { id: "bark", title: "Get close to tree bark", label: "a close-up photo of tree bark" },
  { id: "water", title: "Find moving water", label: "a photo of a creek or river" },
  { id: "sunset", title: "Catch the sunset", label: "a photo of a sunset" },
  { id: "dog", title: "Meet a dog on a walk", label: "a photo of a dog outdoors" },
  { id: "web", title: "Find a spider web", label: "a photo of a spider web" },
  { id: "rock", title: "Find an interesting rock", label: "a photo of a rock" },
];

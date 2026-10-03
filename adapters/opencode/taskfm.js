// taskfm OpenCode plugin
//
// Starts music matched to the task when a prompt lands in the session: the first
// text of every user message is handed to `taskfm start`, which classifies it and
// plays a Spotify station. Playback is spawned detached so the agent never waits.
//
// Opt out:        TASKFM_DISABLE=1
// Custom binary:  TASKFM_BIN=/path/to/taskfm
//
// Install: copy this file to ~/.config/opencode/plugins/taskfm.js
import { spawn } from "child_process";

const BIN = process.env.TASKFM_BIN || "taskfm";

export const TaskFMPlugin = async () => {
  // `message.updated` carries the role, `message.part.updated` carries the text.
  // Correlate them by message ID so assistant output never changes the music.
  const userMessages = new Set();
  const handledParts = new Set();

  const play = (prompt) => {
    if (process.env.TASKFM_DISABLE) return;
    try {
      const child = spawn(BIN, ["start", "-q", "--", prompt], {
        stdio: "ignore",
        detached: true,
      });
      child.on("error", (err) => console.error(`[taskfm] ${BIN}: ${err.message}`));
      child.unref();
    } catch {
      // taskfm missing or blocked - never interrupt the session over music.
    }
  };

  return {
    event: async ({ event }) => {
      const props = event.properties;
      if (!props) return;

      if (event.type === "message.updated") {
        const info = props.info;
        if (info && info.role === "user" && info.id) userMessages.add(info.id);
        return;
      }

      if (event.type !== "message.part.updated") return;
      const part = props.part;
      if (!part || part.type !== "text") return;
      if (!userMessages.has(part.messageID)) return;
      if (handledParts.has(part.id)) return;

      handledParts.add(part.id);
      const prompt = String(part.text || "").trim();
      if (prompt) play(prompt);
    },
  };
};

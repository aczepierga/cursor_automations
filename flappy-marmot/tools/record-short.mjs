// Renders short.html (auto-playing game + captions) to a 1080x1920 mp4.
//
//   node flappy-marmot/tools/record-short.mjs [out.mp4] [seconds] [seed]
//
// Needs Playwright (npm i -D playwright) and ffmpeg on PATH.
//
// The page runs on a virtual clock: time only moves when we step it, and we
// screenshot after every frame. That makes the render frame-exact on any
// machine and, with a fixed random seed, fully reproducible. It also writes
// <out>.timeline.json (caption + game-event times in video seconds), which
// tools/voiceover.py uses to add narration, SFX and music.
import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { join, extname, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = resolve(process.argv[2] || "flappy-marmot-short.mp4");
const SECONDS = Number(process.argv[3] || 38);
const SEED = Number(process.argv[4] || 7);
const FPS = 30;
const SUBSTEPS = 2; // game ticks per video frame (keeps physics at 60 Hz)
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };

// Injected into every frame before page scripts run. The iframe delegates to
// the top frame so the game and the captions share one clock.
const VIRTUAL_TIME = `(() => {
  if (window !== window.top) {
    const top = window.top;
    performance.now = () => top.performance.now();
    window.requestAnimationFrame = cb => top.requestAnimationFrame(cb);
    Math.random = () => top.Math.random();
    return;
  }
  let now = 0, queue = [], seed = ${SEED} >>> 0;
  performance.now = () => now;
  window.requestAnimationFrame = cb => queue.push(cb);
  window.cancelAnimationFrame = () => {};
  Math.random = () => {           // mulberry32
    seed = (seed + 0x6d2b79f5) >>> 0;
    let t = seed;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  window.__step = ms => {
    now += ms;
    const q = queue; queue = [];
    for (const cb of q) cb(now);
  };
})();`;

const server = createServer(async (req, res) => {
  try {
    const path = join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!path.startsWith(ROOT)) throw new Error("outside root");
    const body = await readFile(path);
    res.writeHead(200, { "content-type": TYPES[extname(path)] || "application/octet-stream" });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise(r => server.listen(0, "127.0.0.1", r));

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}
);
const context = await browser.newContext({ viewport: { width: 720, height: 1280 }, deviceScaleFactor: 1.5 });
await context.addInitScript(VIRTUAL_TIME);
const page = await context.newPage();
page.on("pageerror", e => console.error("page error:", e.message));
await page.goto(`http://127.0.0.1:${server.address().port}/short.html`, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);

const ffmpeg = spawn("ffmpeg", [
  "-loglevel", "error", "-y",
  "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
  "-vf", "scale=1080:1920:flags=lanczos",
  "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
  "-movflags", "+faststart", OUT,
], { stdio: ["pipe", "inherit", "inherit"] });

const frames = Math.round(SECONDS * FPS);
for (let i = 0; i < frames; i++) {
  for (let s = 0; s < SUBSTEPS; s++) {
    await page.evaluate(ms => window.__step(ms), 1000 / FPS / SUBSTEPS);
  }
  // Let postMessage events between the frames land before we capture.
  await page.evaluate(() => new Promise(r => setTimeout(r, 0)));
  const shot = await page.screenshot({ type: "jpeg", quality: 92 });
  if (!ffmpeg.stdin.write(shot)) await new Promise(r => ffmpeg.stdin.once("drain", r));
  if (i % (FPS * 5) === 0) process.stdout.write(`\r${(i / FPS).toFixed(0)}s / ${SECONDS}s`);
}
ffmpeg.stdin.end();
await new Promise((r, j) => ffmpeg.on("close", code => (code ? j(new Error(`ffmpeg ${code}`)) : r())));

const timeline = await page.evaluate(() => window.shortTimeline());
await browser.close();
server.close();

await writeFile(OUT.replace(/\.mp4$/, "") + ".timeline.json",
  JSON.stringify({
    duration: SECONDS, seed: SEED, captions: timeline.captions,
    events: Object.fromEntries(Object.entries(timeline.events).map(([k, t]) => [k, +t.toFixed(3)])),
  }, null, 2));
console.log(`\nSaved ${OUT}`);

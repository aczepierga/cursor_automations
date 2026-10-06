# Flappy Marmot 🦫

Flappy Bird, but the bird is a marmot (well, a beaver, because there is no
marmot emoji) and **gravity flips every 5 seconds**.

- `index.html` is the game. Tap or press space to flap. `?bot` makes it play itself,
  `?bot&panic=3` makes the bot freeze on the 3rd gravity flip, and `?mute` turns sound off.
- `short.html` is the YouTube Short: the game plays itself with timed captions
  and voice-over lines.

## Rendering the Short (fully automatic)

```bash
npm i -D playwright                     # or use a global install
node flappy-marmot/tools/record-short.mjs short.mp4          # 1080x1920, silent + short.timeline.json

pip install kokoro-onnx soundfile numpy
# download kokoro-v1.0.int8.onnx + voices-v1.0.bin from
# https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0
# into flappy-marmot/tools/models/
python flappy-marmot/tools/voiceover.py short.mp4            # -> short-final.mp4
```

`record-short.mjs` renders frame by frame on a virtual clock with a fixed random
seed, so every run gives the same video. `voiceover.py` adds an AI narrator
(Kokoro TTS), sound effects and synthesised 8-bit music, all timed to the game
events. Nothing in the output needs licensing.

To make a new episode, edit `CAPTIONS` in `short.html`. Each entry is
`[game event, delay, duration, caption, narration]`.

## Upload details

**Title:** I asked AI to make Flappy Bird… but gravity flips every 5 seconds 🙃

**Description:**
> I asked AI to build Flappy Bird with a marmot. Then I added one rule: gravity flips every 5 seconds.
> It did not go well for the marmot. 💀
>
> 👇 Comment the NEXT dumb rule and I'll add it in the next episode.
>
> #shorts #gamedev #ai #flappybird #indiegame

**Tags:** flappy bird, ai game, gamedev, ai coding, funny game, indie game, marmot

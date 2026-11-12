---
name: generate-image
description: "Makes or fixes an image asset from a reference image. Processes the reference locally (crop, resize, trim, transparent background, format conversion, compression) when that can meet the quality bar, and generates a new asset through an installed image-capable CLI agent (codex, then agy) when the source is too small or too poor. Use when a task needs an icon, logo, illustration, or other image file made from a reference."
---

# Generate image

Make the asset with local tools when the reference is good enough. Generate a new one with another CLI agent only when it is not. Never accept a result you have not measured and looked at.

## 1. Detect tools

Check, do not assume. Tools differ by machine.

```sh
for c in magick sips ffmpeg pngquant oxipng cwebp vips rembg uv uvx codex agy gemini jq; do printf '%s: ' "$c"; command -v "$c" || echo missing; done
```

- `magick` is ImageMagick 7. Use `magick`, not the deprecated `convert`.
- `sips` ships with macOS only.
- `gm` is often a shell alias for `git merge`. Do not assume it is GraphicsMagick.
- Python tools (Pillow, `rembg`) may be missing. `rembg` is not a Homebrew formula.

**Installs need consent.** Before you install anything (Homebrew, `uv`, `uvx`, `pip`, `npx`, a CLI extension, or a model download such as the one `rembg` makes on first use), ask the user and give a one-line purpose, for example: "Install rembg with uv to cut the subject out of a photo background (downloads a model)." Wait for a yes. `uv run --with <pkg>` and `uvx <pkg>` download packages, so they count as installs.

The measuring and verification steps below use `magick`. If neither `magick` nor `sips` exists, you cannot measure the reference. Ask the user to approve installing ImageMagick, for example: "Install ImageMagick to measure, edit, and verify the image." If they decline, stop and say what is missing. With `sips` but no `magick`, you can measure and resize, but the alpha check, the key-out, and the preview in step 4 need ImageMagick, so ask to install it when the task needs those.

## 2. Set the target

1. Find where the asset will show and its displayed size in CSS pixels (from the CSS, the component props, or the task). If nothing states it, ask, or pick the largest size the layout allows and say so in the report.
2. Set the pixel target to the displayed size times 2. Use 3 for icons shown at 64 CSS pixels or less. A 200x100 hero shown at that size needs at least 400x200 pixels. A 32 px icon needs at least 96x96.
3. Note whether the asset needs a transparent background, and which format the project uses (PNG, WebP, JPEG, SVG).
4. Measure the reference:

```sh
magick identify -format '%w x %h %[channels] opaque=%[opaque]\n' REF.png
sips -g pixelWidth -g pixelHeight -g hasAlpha REF.png   # macOS only
```

A channels value that ends in `a` means the file has an alpha channel: `srgba 4.0` for color, `graya 2.0` for grayscale. `srgb 3.0` means it has none. `opaque=False` means at least one pixel is transparent. A file can be `srgba` with `opaque=True`, which means it has an alpha channel but no transparent pixel, so check both. Do not use `%A`, and do not trust `%[fx:p{x,y}.a]` on a file without alpha; it returns a number anyway.

5. Look at the reference image itself. Note blur, JPEG blocks, watermarks, text, and how the subject meets the background.

## 3. Decide: local or generate

Process locally when all of these hold:

- The region you need is at least the pixel target, or at most 1.5 times smaller. Do not upscale a raster source further than 1.5 times and call it done. Never upscale line art, text, or logos at all; generate or ask for a vector.
- The source is sharp at the target size, with no blocks, blur, or watermark in the part you keep.
- If transparency is needed, the background is flat or close to it, so a key-out leaves clean edges.

Skip straight to generation when any of these fail. Do not spend effort on a crop that cannot reach the bar. Also go to generation when a local result fails verification in step 4 and one more local attempt will not fix it.

If generation is not possible (section 5 finds no generator) and local processing cannot reach the bar, stop. Tell the user what the target is, what the source gives, and what is missing.

## 4. Process locally and verify

Work on copies in a scratch directory. These commands ran on a test image with ImageMagick 7.1.2, pngquant 3.0.3, oxipng 10.2.1, and cwebp 1.6.0.

```sh
magick IN.png -crop 800x600+100+50 +repage OUT.png        # crop W x H at offset X,Y
magick IN.png -resize 400x400 OUT.png                     # fit inside 400x400, keeps aspect
sips -Z 1024 IN.png --out OUT.png                         # macOS: longest edge 1024
magick IN.png -filter Lanczos -resize 150% OUT.png        # upscale, 1.5x at most
magick IN.png -trim +repage OUT.png                       # cut uniform border
sips -s format png IN.jpg --out OUT.png                   # macOS: convert format
```

Transparent background:

```sh
# Flood from the corner. Keeps same-colored areas inside the subject.
magick IN.png -alpha set -fuzz 10% -fill none -floodfill +0+0 white OUT.png
# Key a solid color everywhere. Also removes that color inside the subject.
magick IN.png -fuzz 20% -transparent '#00ff00' OUT.png
```

Prefer the flood fill. `-transparent white` on a white-background icon also erased its white inner bar in the test. Set the flood color to the background color (read it with `magick IN.png -format '%[pixel:p{0,0}]\n' info:`), and raise `-fuzz` until the background clears but the subject stays. A flood from one corner does not reach background enclosed by the subject; flood those seed points too, or generate.

Compress last:

```sh
pngquant --quality 65-90 --output OUT.png -- IN.png       # lossy PNG palette, keeps alpha
oxipng -o 4 --strip safe FILE.png                         # lossless, in place
cwebp -q 80 -alpha_q 100 IN.png -o OUT.webp               # WebP with alpha
```

Verify every result before you accept it:

1. Run the `magick identify` line from step 2. The size must meet the target. When transparency was asked for, it must print `opaque=False` and a channels value that ends in `a` (for example `srgba` or `graya`).
2. Render a preview over a solid color that the subject does not use, then view the preview image with your image-reading tool:

```sh
magick OUT.png -background '#2050ff' -alpha remove -alpha off PREVIEW.png
```

Some viewers show fully transparent pixels as black and reveal stray color hidden in them, which looks like specks. The preview shows what a page will show. Check for halos, leftover background, cut-off parts, and a fake checkerboard.

## 5. Generate

Use the first generator that `command -v` finds, in this order: `codex`, `agy`, then any other CLI that can make images (for example `gemini` with an image extension; not confirmed here, check its `--help` first). `claude` and `opencode` cannot generate images on their own; do not try them.

Rules for every generator run:

- Each run spends the user's usage. Make at most 3 attempts per asset in total. Do not loop.
- Run it from a new scratch directory that holds only the reference: `SCRATCH=$(mktemp -d) && cp REF.png "$SCRATCH/ref.png"`. Never point it at the project. Print the path, note it, and write the literal path in later commands when your shell does not keep variables between commands.
- If a command fails, run `<cli> --version` and `<cli> --help` (or `codex exec --help`) before the next attempt. These CLIs change fast.
- Ask for a size large enough for the target. Both tested generators chose their own size (1024 to 1254 px square), which covers a displayed size up to about 500 CSS pixels at 2x (step 2). For a larger target, tell the user the generated asset falls short and how far.
- Ask for transparency, but expect to key it out yourself. If the result has no real alpha, the next attempt asks for a flat solid background in a color the subject does not use (for example `#00ff00`), which keys out cleanly with the commands in step 4.

### codex (confirmed, codex-cli 0.167.2)

`$imagegen` in the prompt calls the built-in `image_gen` tool. It saves to `~/.codex/generated_images/<session-id>/` and takes no path, so the prompt tells Codex to copy the file. `-i` takes several files, so put the prompt before `-i`.

```sh
codex exec --sandbox workspace-write --skip-git-repo-check -C "$SCRATCH" -o "$SCRATCH/codex-last.txt" \
  '$imagegen Make <what> based on the attached reference image. <style, colors>. No text. Transparent background. Then copy the generated PNG to '"$SCRATCH"'/gen.png and print its path.' \
  -i "$SCRATCH/ref.png" < /dev/null
```

In the test this exited 0 after 79 seconds, used the reference, and wrote a 1254x1254 PNG with real alpha (`srgba`, `opaque=False`). The stderr log shows the session id. The test ran without `< /dev/null` and printed "Reading additional input from stdin..."; the redirect gives Codex an empty stdin so it cannot wait on one (the redirect itself was not run in the test; unconfirmed here).

### agy, Google Antigravity CLI (partly confirmed, agy 1.5.6)

Use agy only when `codex` is missing. Before the first agy run in a session, tell the user that agy will run with `--dangerously-skip-permissions`, which lets it run any command as the user, and that it may read files outside the scratch directory and install packages. Those installs break the ask-before-install rule in step 1, and nothing in this skill can stop them.

Before you run agy, check that `jq` exists, because the transcript check below needs it. If it is missing, ask the user to approve installing `jq`, for example: "Install jq to list what agy did." If they decline, do not use agy.

agy has no image-attach flag, so name the reference by absolute path. Its `generate_image` tool (run by an `image-generator` subagent) takes that path as input. `-p` takes the next argument as the prompt, so put every flag before `-p "<prompt>"`; `-p --dangerously-skip-permissions` fails with exit 2. Antigravity's headless docs say that without `--dangerously-skip-permissions` a headless run silently skips steps that need approval and still exits 0 (unconfirmed here). Upstream issue reports say `-p` can hang without a terminal (unconfirmed here; the test run, with stdin from `/dev/null`, did not hang), so close stdin and set `--print-timeout`.

```sh
cd "$SCRATCH" && agy --dangerously-skip-permissions --output-format json --print-timeout 300s \
  -p "Use the generate_image tool to make <what> based on the reference image at $SCRATCH/ref.png. <style, colors>. No text. Solid #00ff00 background. Then copy the generated image to $SCRATCH/gen.png and print its path. Do not read other files and do not install anything." \
  < /dev/null > "$SCRATCH/agy.json"
```

In the test this exited 0 after 267 seconds and used the reference. The image was done after about one minute. In the rest of the run agy read other files in the scratch directory, read its own old conversation databases with `sqlite3`, ran `find <dir> -maxdepth 3` on a directory two levels above its working directory, ran `head` on unrelated files outside the scratch directory, and ran `uv run --with pillow` twice, which put Pillow in the uv cache without asking anyone. The scratch directory limits none of this; it only keeps unrelated project files out of agy's starting view. The test prompt had neither the "Solid #00ff00 background" sentence nor the last sentence, so whether either works with agy is unconfirmed.

The JSON output holds only `conversation_id`, `status`, `response`, duration, and usage, with no record of tool calls, and stderr was empty. agy keeps a transcript per conversation and per subagent. This read-only command listed every tool call of the test run, including the subagent's `generate_image`:

```sh
B=~/.gemini/antigravity-cli/brain; ID=$(jq -r .conversation_id "$SCRATCH/agy.json")
for c in "$ID" $(ls "$B/$ID/.system_generated/subagents" | sed 's/\.json$//'); do
  jq -r 'select(.tool_calls) | .tool_calls[] | "\(.name) \(.args | tostring)"' "$B/$c/.system_generated/logs/transcript.jsonl"
done
```

Run it after every agy run. This layout is undocumented and may change. `agy --help` also lists `--sandbox` ("Run in a sandbox with terminal restrictions enabled") and `--mode` (`accept-edits`, `auto`, `plan`); neither was tried, so whether they limit reads or installs is unconfirmed.

The tool wrote a 1024x1024 JPEG (`srgb`, no alpha) with a fake checkerboard where transparency was asked for, under `~/.gemini/antigravity-cli/brain/<conversation_id>/`. A corner flood with `-fuzz 25%` from white cleared that checkerboard in the test, but a solid key color is safer.

## 6. Place the result and report

1. Copy the result into the project at a new path. Never overwrite an existing asset. If `hero.png` exists, write `hero-v2.png` (or the next free number) and update references only if the task asks for it.
2. Re-run the checks in step 4 on the copied file: pixel size, `opaque=False` and a channels value ending in `a` when transparency was asked for, and a viewed preview.
3. If it fails, fix it locally (key out the background, resize, compress) or make one more generator attempt with a sharper prompt, within the cap of 3.
4. Report the final absolute path, pixel size, channels, file size, and how it was made: which local commands, or which generator and prompt, and what you fixed afterwards. List any scratch files and generator output folders you left. If agy ran, list every package it installed and every path outside the scratch directory it read or wrote, as its transcript shows them.

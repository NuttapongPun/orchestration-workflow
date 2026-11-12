---
name: generate-image
description: "Makes or fixes an image asset, from a reference image or from a description alone. Processes a reference locally (crop, resize, trim, transparent background, format conversion, compression) when that can meet the quality bar, and generates a new image through an installed image-capable CLI agent (codex, then agy) when the source is too small or too poor, or when there is no reference. Decides whether text is generated in the image, added locally, or left to HTML. Use when a task needs an icon, logo, illustration, banner, hero image, ad, or other image file, made from a reference or from a request such as \"generate a banner for X\"."
---

# Generate image

Make the asset with local tools when a reference is good enough. Generate a new one with another CLI agent when it is not, or when there is no reference. Never accept a result you have not measured and looked at.

## 1. Detect tools

Check, do not assume. Tools differ by machine.

```sh
for c in magick sips ffmpeg pngquant oxipng cwebp vips rembg uv uvx codex agy gemini jq; do printf '%s: ' "$c"; command -v "$c" || echo missing; done
```

- `magick` is ImageMagick 7. Use `magick`, not the deprecated `convert`.
- `sips` ships with macOS only.
- `gm` is often a shell alias for `git merge`. Do not assume it is GraphicsMagick.
- Python tools (Pillow, `rembg`) may be missing. `rembg` is not a Homebrew formula.

**Installs need consent.** Before you install anything (Homebrew, `uv`, `uvx`, `pip`, `npx`, a CLI extension, a font, or a model download such as the one `rembg` makes on first use), ask the user and give a one-line purpose, for example: "Install rembg with uv to cut the subject out of a photo background (downloads a model)." Wait for a yes. `uv run --with <pkg>` and `uvx <pkg>` download packages, so they count as installs.

The measuring and verification steps below use `magick`. If neither `magick` nor `sips` exists, you cannot measure the reference or the result. Ask the user to approve installing ImageMagick, for example: "Install ImageMagick to measure, edit, and verify the image." If they decline, stop and say what is missing. With `sips` but no `magick`, you can measure and resize, but the alpha check, the key-out, the ratio crop, the text overlay, and the preview in step 5 need ImageMagick, so ask to install it when the task needs those.

## 2. Set the target

1. Find where the asset will show and its displayed size in CSS pixels (from the CSS, the component props, or the task). If nothing states it, ask, or pick the largest size the layout allows and say so in the report. When you will generate, hold this question for the brief message in step 4.
2. Set the pixel target to the displayed size times 2. Use 3 for icons shown at 64 CSS pixels or less. A 200x100 hero shown at that size needs at least 400x200 pixels. A 32 px icon needs at least 96x96. A banner shown 1200 CSS px wide needs 2400 px.
3. Note whether the asset needs a transparent background, and which format the project uses (PNG, WebP, JPEG, SVG).

With a reference, also do 4 and 5. Without one, skip them.

4. Measure the reference:

```sh
magick identify -format '%w x %h %[channels] opaque=%[opaque]\n' REF.png
sips -g pixelWidth -g pixelHeight -g hasAlpha REF.png   # macOS only
```

A channels value that ends in `a` means the file has an alpha channel: `srgba 4.0` for color, `graya 2.0` for grayscale. `srgb 3.0` means it has none. `opaque=False` means at least one pixel is transparent. A file can be `srgba` with `opaque=True`, which means it has an alpha channel but no transparent pixel, so check both. Do not use `%A`, and do not trust `%[fx:p{x,y}.a]` on a file without alpha; it returns a number anyway.

5. Look at the reference image itself. Note blur, JPEG blocks, watermarks, text, and how the subject meets the background.

## 3. Decide: local or generate

With no reference, there is nothing to measure or process. Write the brief in step 4 and generate (step 6). Steps 2, 5, and 7 still apply to the result: the target size, the crop, the text overlay, verification, and placement.

With a reference, process locally when all of these hold:

- The region you need is at least the pixel target, or at most 1.5 times smaller. Do not upscale a raster source further than 1.5 times and call it done. Never upscale line art, text, or logos at all; generate or ask for a vector.
- The source is sharp at the target size, with no blocks, blur, or watermark in the part you keep.
- If transparency is needed, the background is flat or close to it, so a key-out leaves clean edges.

When any of these fail, write the brief in step 4 and generate (step 6). Do not spend effort on a crop that cannot reach the bar. Also go to generation when a local result fails verification in step 5 and one more local attempt will not fix it.

If step 6 finds no generator, and either there is no reference or local processing cannot reach the bar, stop. Tell the user what the target is, what the source gives, and what is missing.

## 4. Write the brief

Before you generate, settle these points. Take what the request and the project state. Look in the project for brand colors, an existing logo, a `DESIGN.md`, and CSS variables. Ask the user only for what neither gives, in one message.

- The subject, and the style (photo, flat illustration, 3D, line art).
- Colors or brand cues.
- The aspect ratio, where the image shows, and its displayed size (step 2).
- Whether it has text, and the exact wording.
- Whether it needs a transparent background.

With a reference, the reference settles most of these.

Decide how to handle text with this rule:

| Situation | Approach |
|---|---|
| One-off image, fixed wording, one language | Generate the text in the image. |
| Several languages, or copy that will be edited later | Generate the art once without text, leaving clear space for it, then add the text per version. |
| Small print, prices, dates, legal lines | Always add locally. Generators get small exact text wrong most often. |
| The request does not say | Ask the user one question: "Will this text change or need other languages?" |

Put that question in the same message as any other brief questions.

**Generated text.** The prompt gives the exact wording in quotes and says to render it exactly with no other text, for example: `Render the headline "Fresh every morning" exactly as written, on the left. Render no other text.` Check the words after every run (step 5). Generators get non-Latin scripts such as Thai wrong more often than English, so expect more failed attempts (a caution, not measured here).

**Text that changes.** Generate one text-free master. The prompt says `No text.` and names the clear space, for example `Leave the left third plain.` (unconfirmed here). Keep the master beside the outputs (`banner-master.png` next to `banner-en.png`), so a later copy change needs no new generation.

- For web use, prefer real HTML and CSS text over the master. It stays sharp at any size, it can be translated, and screen readers and search engines can read it.
- For image-only outputs such as ad uploads, overlay the text locally with `magick` (step 5), one file per language from the same master.
- An option (unconfirmed here): give the generator the finished image as the reference and ask it to change only the wording. Check it like any generated text; each run counts against the cap.

## 5. Process locally and verify

Work on copies in a scratch directory. These commands ran on a test image with ImageMagick 7.1.2, pngquant 3.0.3, oxipng 10.2.1, and cwebp 1.6.0.

```sh
magick IN.png -crop 800x600+100+50 +repage OUT.png        # crop W x H at offset X,Y
magick IN.png -gravity center -crop 3:1 +repage OUT.png   # crop to an exact 3:1 ratio, centered
magick IN.png -resize 400x400 OUT.png                     # fit inside 400x400, keeps aspect
sips -Z 1024 IN.png --out OUT.png                         # macOS: longest edge 1024
magick IN.png -filter Lanczos -resize 150% OUT.png        # upscale, 1.5x at most
magick IN.png -trim +repage OUT.png                       # cut uniform border
sips -s format png IN.jpg --out OUT.png                   # macOS: convert format
```

On a 2172x724 generated banner, the ratio crop gave 2172x543 for `4:1` and 1287x724 for `16:9`.

Transparent background:

```sh
# Flood from the corner. Keeps same-colored areas inside the subject.
magick IN.png -alpha set -fuzz 10% -fill none -floodfill +0+0 white OUT.png
# Key a solid color everywhere. Also removes that color inside the subject.
magick IN.png -fuzz 20% -transparent '#00ff00' OUT.png
```

Prefer the flood fill. `-transparent white` on a white-background icon also erased its white inner bar in the test. Set the flood color to the background color (read it with `magick IN.png -format '%[pixel:p{0,0}]\n' info:`), and raise `-fuzz` until the background clears but the subject stays. A flood from one corner does not reach background enclosed by the subject; flood those seed points too, or generate.

Add text locally, after any resize, so the text is drawn at the final size:

```sh
magick MASTER.png -font '/System/Library/Fonts/Supplemental/Arial Bold.ttf' -pointsize 64 -fill '#3b1f0e' \
  -gravity northwest -annotate +100+90 'Open daily from 7 am' OUT-en.png
```

`-gravity` and `-annotate +X+Y` set where the text starts. The font path in the command exists on macOS only; on other systems, substitute a font file that exists there. The overlay writes an `srgba` file with `opaque=True` from an `srgb` input, which is normal and not a fault. Pass a font file path to `-font`; `magick -list font` printed nothing on this machine, so font names had nothing to resolve against. Before you use a font for a script, render a short sample with it and view it. If no font on the machine covers the script, asking to install one is an install under step 1.

This ImageMagick build lists no `raqm` among its delegates (`magick -version`), so it does not shape complex scripts; the font decides. In a Thai test (`สดใหม่ทุกเช้า ที่นี่ น้ำ ปั้น`), `Thonburi.ttc` drew the tone and vowel marks as separate glyphs on dotted circles, `Silom.ttf` drew the tone marks over the vowel marks, where they could not be seen, and `Ayuthaya.ttf` and `SukhumvitSet.ttc` (both in `/System/Library/Fonts/Supplemental/`) placed every mark correctly. Whether a build with `raqm` shapes Thai, and how Arabic or Indic scripts render, is unconfirmed here. For these scripts, prefer HTML text on the web, and view every overlay at full size.

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

3. When the image has text, view it at full size and compare every word and character with the requested copy. A wrong, missing, or extra word fails the result. For generated text, that is a failed attempt and counts against the cap of 3 in step 6.

## 6. Generate

Use the first generator that `command -v` finds, in this order: `codex`, `agy`, then any other CLI that can make images (for example `gemini` with an image extension; not confirmed here, check its `--help` first). `claude` and `opencode` cannot generate images on their own; do not try them.

Rules for every generator run:

- Each run spends the user's usage. Make at most 3 attempts per asset in total. Do not loop.
- Run it from a new scratch directory that holds only the reference, or nothing when there is none: `SCRATCH=$(mktemp -d)`, then `cp REF.png "$SCRATCH/ref.png"` when there is a reference. Never point it at the project. Print the path, note it, and write the literal path in later commands when your shell does not keep variables between commands.
- If a command fails, run `<cli> --version` and `<cli> --help` (or `codex exec --help`) before the next attempt. These CLIs change fast.
- Follow the text rule in step 4. In the prompts below, `<text>` is the quoted wording with "Render no other text.", or `No text.` with the clear space named when text will be added later, or plain `No text.` when the image has none.
- After every run, run the checks in step 5, including the text check.
- Ask for transparency, but expect to key it out yourself. If the result has no real alpha, the next attempt asks for a flat solid background in a color the subject does not use (for example `#00ff00`), which keys out cleanly with the commands in step 5.

The generators pick their own size. Past `codex` outputs here were 1254 to 2172 px on the long edge (1254x1254, 1536x1024, 1844x853, 2172x724), and `agy` gave 1024x1024. A 1024 px edge covers about 500 CSS pixels at 2x, so a wide banner often falls short. So:

1. Ask for the aspect ratio in the prompt, for example "Landscape, aspect ratio 3:1."
2. Measure what comes back with the identify line in step 2, and crop to the exact ratio with the ratio crop in step 5.
3. If it is still below the target, upscale at most 1.5x, under the rule in step 3. Never upscale an image with generated text. A text-free master avoids this: upscale the master, then add the text at the final size with HTML or a local overlay.
4. Tell the user plainly when the result still falls short of the 2x target, and by how much, for example: "The banner shows 1200 CSS px wide and needs 2400 px. It is 2172 px, 228 px short, which is 1.8x."

### codex (confirmed, codex-cli 0.167.2)

`$imagegen` in the prompt calls the built-in `image_gen` tool. It saves to `~/.codex/generated_images/<session-id>/` and takes no path, so the prompt tells Codex to copy the file. `-i` takes several files, so put the prompt before `-i`.

With a reference:

```sh
codex exec --sandbox workspace-write --skip-git-repo-check -C "$SCRATCH" -o "$SCRATCH/codex-last.txt" \
  '$imagegen Make <what> based on the attached reference image. <style, colors>. <text>. Transparent background. Then copy the generated PNG to '"$SCRATCH"'/gen.png and print its path.' \
  -i "$SCRATCH/ref.png" < /dev/null
```

In the test this exited 0 after 79 seconds, used the reference, and wrote a 1254x1254 PNG with real alpha (`srgba`, `opaque=False`). That test ran without `< /dev/null`; this form with the redirect has not run (unconfirmed here).

Without a reference, drop `-i` and the reference sentence:

```sh
codex exec --sandbox workspace-write --skip-git-repo-check -C "$SCRATCH" -o "$SCRATCH/codex-last.txt" \
  '$imagegen Make <what>. <style, colors>. <orientation>, aspect ratio <W:H>. <text>. Then copy the generated PNG to '"$SCRATCH"'/gen.png and print its path.' \
  < /dev/null
```

Add "Transparent background." to the prompt when the asset needs one.

In the test, from an empty scratch directory, this asked for a 3:1 coffee shop banner with the headline "Fresh every morning". It exited 0 after 52 seconds and wrote a 2172x724 PNG (`srgb`, no alpha), exactly 3:1, with every word of the headline correct. Codex still printed "Reading additional input from stdin..." to stderr, then ran to the end without waiting. The stderr log shows the session id.

### agy, Google Antigravity CLI (partly confirmed, agy 1.5.6)

Use agy only when `codex` is missing. Before the first agy run in a session, tell the user that agy will run with `--dangerously-skip-permissions`, which lets it run any command as the user, and that it may read files outside the scratch directory and install packages. Those installs break the ask-before-install rule in step 1, and nothing in this skill can stop them.

Before you run agy, check that `jq` exists, because the transcript check below needs it. If it is missing, ask the user to approve installing `jq`, for example: "Install jq to list what agy did." If they decline, do not use agy.

agy has no image-attach flag, so name the reference by absolute path. Its `generate_image` tool (run by an `image-generator` subagent) takes that path as input. `-p` takes the next argument as the prompt, so put every flag before `-p "<prompt>"`; `-p --dangerously-skip-permissions` fails with exit 2. Antigravity's headless docs say that without `--dangerously-skip-permissions` a headless run silently skips steps that need approval and still exits 0 (unconfirmed here). Upstream issue reports say `-p` can hang without a terminal (unconfirmed here; the test run, with stdin from `/dev/null`, did not hang), so close stdin and set `--print-timeout`.

```sh
cd "$SCRATCH" && agy --dangerously-skip-permissions --output-format json --print-timeout 300s \
  -p "Use the generate_image tool to make <what> based on the reference image at $SCRATCH/ref.png. <style, colors>. <text>. Solid #00ff00 background. Then copy the generated image to $SCRATCH/gen.png and print its path. Do not read other files and do not install anything." \
  < /dev/null > "$SCRATCH/agy.json"
```

In the test this exited 0 after 267 seconds and used the reference. The image was done after about one minute. In the rest of the run agy read other files in the scratch directory, read its own old conversation databases with `sqlite3`, ran `find <dir> -maxdepth 3` on a directory two levels above its working directory, ran `head` on unrelated files outside the scratch directory, and ran `uv run --with pillow` twice, which put Pillow in the uv cache without asking anyone. The scratch directory limits none of this; it only keeps unrelated project files out of agy's starting view. The test prompt had neither the "Solid #00ff00 background" sentence nor the last sentence, and its text was `No text.`. So whether either sentence works with agy, and whether agy renders generated text correctly, is unconfirmed.

Without a reference, drop "based on the reference image at $SCRATCH/ref.png" and add the aspect ratio. That variant has not run (unconfirmed here).

The JSON output holds only `conversation_id`, `status`, `response`, duration, and usage, with no record of tool calls, and stderr was empty. agy keeps a transcript per conversation and per subagent. This read-only command listed every tool call of the test run, including the subagent's `generate_image`:

```sh
B=~/.gemini/antigravity-cli/brain; ID=$(jq -r .conversation_id "$SCRATCH/agy.json")
for c in "$ID" $(ls "$B/$ID/.system_generated/subagents" | sed 's/\.json$//'); do
  jq -r 'select(.tool_calls) | .tool_calls[] | "\(.name) \(.args | tostring)"' "$B/$c/.system_generated/logs/transcript.jsonl"
done
```

Run it after every agy run. This layout is undocumented and may change. `agy --help` also lists `--sandbox` ("Run in a sandbox with terminal restrictions enabled") and `--mode` (`accept-edits`, `auto`, `plan`); neither was tried, so whether they limit reads or installs is unconfirmed.

The tool wrote a 1024x1024 JPEG (`srgb`, no alpha) with a fake checkerboard where transparency was asked for, under `~/.gemini/antigravity-cli/brain/<conversation_id>/`. A corner flood with `-fuzz 25%` from white cleared that checkerboard in the test, but a solid key color is safer.

## 7. Place the result and report

1. Copy the result into the project at a new path. Never overwrite an existing asset. If `hero.png` exists, write `hero-v2.png` (or the next free number) and update references only if the task asks for it. Place a text-free master beside its outputs.
2. Re-run the checks in step 5 on the copied file: pixel size, `opaque=False` and a channels value ending in `a` when transparency was asked for, a viewed preview, and every word of any text.
3. If it fails, fix it locally (key out the background, crop, resize, overlay text, compress) or make one more generator attempt with a sharper prompt, within the cap of 3.
4. Report the final absolute path, pixel size, channels, file size, and how it was made: which local commands, or which generator and prompt, and what you fixed afterwards. Say how far the size falls short of the target, if it does. List any scratch files and generator output folders you left. If agy ran, list every package it installed and every path outside the scratch directory it read or wrote, as its transcript shows them.

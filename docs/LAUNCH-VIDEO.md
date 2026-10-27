# Dark launch video

**One idea, said once:** a screenshot is not proof — a replayable scenario with the
evidence attached is.

Everything on screen comes from a real run of the Dark Desktop Fixture. No invented
logs, no invented numbers, no stock UI.

## Deliverables

| Cut | Size | Length | Use |
|---|---|---|---|
| `dark-launch` | 1920×1080 @ 30fps | 79s (2370 frames) | X, YouTube, HN, Vercel landing page |
| `dark-launch-vertical` | 1080×1920 @ 30fps | 30s (900 frames) | Reels, Shorts, TikTok |
| `dark-launch-bumper` | 1920×1080 @ 30fps | 6s (180 frames) | Pre-roll, docs hero loop |

Frame 0 of the master is also the thumbnail: the fixture status line
`Saved quantity: -2` inside a red box, everything else black.

## Master timeline (79s)

| # | Time | Frames | Visual | On-screen text | VO |
|---|---|---|---|---|---|
| 1 | 0:00–0:06 | 180 | Crop of the real fixture window: quantity `-2`, status `Saved quantity: -2`. Red rect draws around the status. | `Saved quantity: -2` / small tag `real app, real input` | This is a real failure. |
| 2 | 0:06–0:14 | 240 | A folder of screenshots — twelve files named `Screenshot 2026-10-26 at 10.42.11.png` — scrolling past, each slightly rotated. | `Proof, or just a picture?` | Most bug reports die here: a screenshot, a half-remembered click path, and no way to run it again. |
| 3 | 0:14–0:21 | 210 | Black. Wordmark `dark` with a mint cursor block. The install line types itself, one character per frame. | `npm install -g dark-agent-cli` / `Test the behavior. Keep the proof.` | Dark is an agent in your terminal that drives Windows apps the way you do. |
| 4 | 0:21–0:24 | 90 | Terminal. `dark desktop doctor`. Output snaps in at 4× speed. | — | Check the adapter first. |
| 5 | 0:24–0:30 | 180 | Terminal. `dark desktop probe --title 'Dark Desktop Fixture' --expect Ready --screenshot`. Output: observed `Ready`, check passed, screenshot path. | `look, don't touch` | Look, don't touch. It reads the real control tree and checks the words on screen. |
| 6 | 0:30–0:36 | 180 | Terminal. `dark desktop exercise examples\desktop\negative.json` — no `--apply`. Output: `preview only · nothing executed`. | `--apply` highlighted, not pressed | Scenarios are reviewed before they run. Without apply, nothing is clicked. |
| 7 | 0:36–0:44 | 240 | Same command `--apply`. Typed `-2`. Save clicked. Output block lands line by line, red `✗`. | `expected  Rejected: quantity must be nonnegative` / `observed  Saved quantity: -2` / `exit code 1` | Expected rejected. It saved negative two. Exit code one. |
| 8 | 0:44–0:52 | 240 | File tree of `.dark/runs/20261026T111910-61871996/`: `scenario.json`, `snapshot.json`, `screenshot.png`, `events.jsonl`, `report.json`. Each gets a one-line label on hover. Then `report.json` crop. | `"verified_finding": false` | Everything needed to replay it sits in one folder. And the report won't call it a vulnerability. |
| 9 | 0:52–1:00 | 240 | Two rule cards, mono, stacked. | `Mutations aren't retried after a timeout.` / `The click may already have landed.` / `Raw evidence stays on your machine.` / `Only the summary uploads.` | A timeout never silently retries a click, because the click may already have landed. Report uploads exclude raw screenshots; agent chat sends observations and requested images to your model provider. |
| 10 | 1:00–1:08 | 240 | `dark runs upload .dark\runs\20261026T111910-61871996 --open`. Browser opens the dashboard: expected vs observed side by side, `failed` badge, red ✗. | `expected` / `observed` | Upload the run, and the dashboard shows expected against observed, per assertion. |
| 11 | 1:08–1:14 | 180 | Black card. Muted mono lines fade in one at a time, no animation flourish. | `no autonomous exploration` / `no web targets yet` / `no CTF yet` / `Windows 10 and 11 only` | It doesn't explore on its own yet. No web targets. No CTF. Windows only. |
| 12 | 1:14–1:19 | 150 | `npm install -g dark-agent-cli` typed, then the URL and the wordmark. | `dark-cli-web.vercel.app` / `Authorized targets only.` | The failure, the proof, and the command to run it again. |

## VO read (158 words, ~120 wpm)

> This is a real failure.
>
> Most bug reports die here: a screenshot, a half-remembered click path, and no way
> to run it again.
>
> Dark is an agent in your terminal that drives Windows apps the way you do.
>
> Check the adapter first.
>
> Look, don't touch. It reads the real control tree and checks the words on screen.
>
> Scenarios are reviewed before they run. Without apply, nothing is clicked.
>
> Expected rejected. It saved negative two. Exit code one.
>
> Everything needed to replay it sits in one folder. And the report won't call it a
> vulnerability.
>
> A timeout never silently retries a click, because the click may already have
> landed. Report uploads send the summary, rather than raw screenshots. Agent chat
> separately sends tool observations and requested screenshots to your model provider.
>
> Upload the run, and the dashboard shows expected against observed, per assertion.
>
> It doesn't explore on its own yet. No web targets. No CTF. Windows only.
>
> The failure, the proof, and the command to run it again.

Read it flat and quiet. No upward inflection on the list in scene 11 — it is a
statement of scope, not an apology. Beat of silence after "one folder."

## Vertical cut (30s)

| Time | Frames | Content |
|---|---|---|
| 0:00–0:04 | 120 | Hook: `Saved quantity: -2` in a red box, mono, full screen. |
| 0:04–0:08 | 120 | `This is a real failure. Here's the proof.` |
| 0:08–0:16 | 240 | Montage, hard cuts on each command: probe → preview → `--apply` → red ✗. |
| 0:16–0:22 | 180 | Report card: expected vs observed, then `"verified_finding": false`. |
| 0:22–0:27 | 150 | Dashboard, expected against observed. |
| 0:27–0:30 | 90 | `npm install -g dark-agent-cli` + wordmark. |

## Visual system

| Token | Value | Use |
|---|---|---|
| base | `#080808` | Every background |
| surface | `#111111` | Terminal frame, cards |
| border | `#1a1a1a` | 1px rules, terminal chrome |
| text | `#f0f0f0` | Body, terminal output |
| muted | `#888888` | Prompts, the scope list |
| accent | `#00ff88` | Cursor, passed checks, `--apply` |
| fail | `#ff5a5f` | `✗`, observed line, red box |

- Type: Inter for prose, JetBrains Mono for terminal and all data. Copy the woff2
  files from `frontend/public/dark/fonts/` into the Remotion `public/` so renders
  never hit the network.
- Minimum sizes at 1080p: 44px body, 96px for a single data line, 28px for labels.
  Nothing below 24px — this gets watched at 390px wide.
- Motion rule: hard cuts, 8-frame type-on for terminal lines, one 6-frame rise for
  cards. No easing flourishes, no particle fields, no AI sparkle. The restraint is
  the brand.
- The red box in scene 1 is the only hand-drawn element in the video; it draws once
  in 12 frames and never repeats.

## Sound

- Keystrokes only for typed commands, matched to the character count.
- One low riser, 1.5s, ending exactly on the `✗` in scene 7.
- Cut all sound for 8 frames before `"verified_finding": false`.
- Music optional and never above −28 LUFS under the read. If in doubt, ship without
  music; the keystrokes carry it.
- Burn captions in. Most feed views are muted, so the on-screen text is the caption
  track — keep it to 3–7 words per card and never duplicate the VO word for word.

## Implementation notes

New compositions live next to the existing explainers, but do not reuse
`Explainer` — that format is a vertical caption reel with a fixed beat model.

- `src/dark-launch/` holds the scenes: `Hook`, `Screenshots`, `Install`, `Terminal`,
  `Report`, `Rules`, `Dashboard`, `Scope`, `Cta`.
- Add `dark-launch`, `dark-launch-vertical` and `dark-launch-bumper` in `Root.tsx`
  with explicit `width`/`height`; `theme.ts` currently hardcodes 1080×1920, so pass
  dimensions per composition instead of changing it.
- One `<Term>` component: fixed line height, caret blink, and an output queue driven
  by `useCurrentFrame()` so every revealed line has a frame-accurate trigger.
- Sequence with `<Series>` and hard cuts; no `<TransitionSeries>` crossfades.
- Hybrid capture is the honest option: record the real fixture window with a screen
  recorder for scenes 1 and 7, and render the terminal in Remotion for crisp text
  and controllable timing. Composite the capture inside the terminal frame so the
  seam disappears.
- The exact strings in scenes 5–8 are in `.dark/runs/20261026T111910-61871996/`.
  Re-record them from a fresh run rather than retyping.

```bash
npx remotion render dark-launch out/dark-launch.mp4 --codec=h264 --crf=16
npx remotion render dark-launch-vertical out/dark-launch-vertical.mp4 --codec=h264 --crf=16
```

## Do not show

- Autonomous scanning, browser targets, or CTF solving — they exit with a
  not-implemented status, and someone will run them.
- Any claim of a "verified finding." The report itself says
  `verified_finding: false`; lead with that instead, it is the more interesting fact.
- Fake dashboards, invented metrics, or a stock "AI" visual language.
- Model benchmarks. There are none yet.

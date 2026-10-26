# Achilles / Dark CLI frontend

A Next.js App Router recreation of the supplied [Achilles Framer project](https://framer.com/projects/Achilles-copy--PAwjxIDRIWUUuNTlXVxB-6Xu0j).

```powershell
npm install
npm run dev
# http://127.0.0.1:3000
```

For production, run `npm run build` followed by `npm start`.
Verification: `npm run lint` and `npm run typecheck`.

## Editing

- `src/components/achilles-landing.tsx`: navigation, hero, feature illustrations, tabs, steps, benefits, testimonials, pricing, FAQ, and footer.
- `src/data/achilles.json`: copy extracted from the connected Framer project's components. Edit this to customize the template content.
- `src/app/globals.css`: original color tokens, locally hosted fonts, layout, breakpoints, and motion.
- `src/components/bands-background.tsx`: WebGL2 renderer for the original Bands shader, with the exact Framer uniform settings. Pauses offscreen/in background tabs and respects reduced motion. Uses original fallback images when WebGL is unavailable.
- `public/framer/`: original downloaded images, SVGs, fonts, and shader. Everything is served locally; no Framer runtime or iframe is required.
- `assets-manifest.json`: source URLs and provenance. `npm run assets:sync` refreshes the downloaded assets. Extracted SVGs and the shader are checked in separately.

The source was inspected through Framer CLI session 1, including its desktop, tablet, and phone layouts, component variants, typography, color tokens, and shader controls. The published template supplied original SVG definitions and the Bands fragment shader. Native React/CSS replaces the template's runtime and interactions.

Achilles branding, sample testimonials, pricing, and outbound template links are intentionally preserved for this recreation. They are template content, not claims about Dark CLI. Dashboard visuals are the original images; the page does not execute agent tasks or collect payments. The existing `/api/*` and `/health` proxy routes remain available; set `DARK_BACKEND_URL` to change their default `http://127.0.0.1:8000` target.

No API credentials are needed for this frontend. Keep model keys in the backend environment.

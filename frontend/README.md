# Dark frontend

A Next.js landing page and account workspace for the Dark CLI. It explains the implemented native
Windows testing workflow: read-only probes, explicit scenario exercises, and
locally saved evidence.

Account pages are available at `/login`, `/connect`, `/dashboard`, and
`/dashboard/runs/<id>`. Sign-in uses email codes; the workspace lists connected
computers and uploaded desktop reports. See [account setup](../docs/AUTH.md)
for MongoDB and Resend email configuration. The landing page's sign-in and
Get started links lead to `/login`; the setup guide remains in the footer.

```powershell
npm install
npm run dev
# http://127.0.0.1:3000
```

Run `npm run lint`, `npm run typecheck`, and `npm run build` to verify changes.
The setup guide links point to the repository's native Windows guide. The
`/api/*` and `/health` proxy routes remain available; `DARK_BACKEND_URL` can
change their default backend target.

## Editing

- `src/components/dark-landing.tsx`: product copy, navigation, CSS-rendered report illustration, tabs, status, FAQ, and footer.
- `src/components/landing-motion.tsx`: entrances and directional scroll reveals. It respects reduced motion and keeps content readable without JavaScript.
- `src/components/bands-background.tsx`: local WebGL2 renderer for the Bands shader, with a static fallback.
- `src/app/globals.css`: fonts, colors, layout, responsive rules, and interaction styles.
- `public/dark/`: the fonts, UI symbols, shader, and fallback textures used by the site.

No API credentials are needed to view this page. The optional Jev decision
preview is a CLI feature and uses a backend environment key, never a frontend
key.

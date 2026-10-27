// UI symbols used by the Dark landing page, drawn with the brand mark's square strokes.
const icons = {
  arrow: <path d="M4 12h15M13 6l6 6-6 6" />,
  check: <path d="M4 12.5l5 5L20 6.5" />,
  eye: <><path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z" /><path d="M10 10h4v4h-4z" /></>,
  play: <><path d="M3 4h18v16H3z" /><path d="M10 9v6l5-3z" /></>,
  file: <><path d="M5 3h9l5 5v13H5z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></>,
  target: <path d="M9 3H3v6M15 3h6v6M21 15v6h-6M9 21H3v-6M8 12h8M12 8v8" />,
  preview: <><path d="M3 5h18M3 12h10M3 19h7" /><path d="M16 15l5 2.5-5 2.5z" /></>,
  pause: <><path d="M4 4h16v16H4z" /><path d="M10 9v6M14 9v6" /></>,
};

export type IconName = keyof typeof icons;

export function Icon({
  name,
  className = "",
}: {
  name: IconName;
  className?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      className={`icon ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="square"
    >
      {icons[name]}
    </svg>
  );
}

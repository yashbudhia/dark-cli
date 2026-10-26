import type { CSSProperties } from "react";

// UI symbols used by the Dark landing page.
const icons = {
  arrow: "1175957644",
  blocks: "4191764975",
  flask: "150931171",
  check: "3338047389",
  hourglass: "2467156701",
  eye: "2222779130",
  branch: "213763526",
  shield: "1513061799",
} as const;

export type IconName = keyof typeof icons;

export function Icon({
  name,
  className = "",
}: {
  name: IconName;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`icon ${className}`}
      style={
        {
          "--icon-url": `url(/dark/icons/${icons[name]}.svg)`,
        } as CSSProperties
      }
    />
  );
}

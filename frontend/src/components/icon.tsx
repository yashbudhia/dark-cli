import type { CSSProperties } from "react";

// Original vector geometry extracted from the published Framer template.
const icons = {
  arrow: "1175957644",
  bug: "1027221055",
  blocks: "4191764975",
  flask: "150931171",
  check: "3338047389",
  hourglass: "2467156701",
  feather: "2245466271",
  rocket: "1317923517",
  eye: "2222779130",
  branch: "213763526",
  shield: "1513061799",
  x: "1688045918",
  linkedin: "4033599021",
  github: "2873462264",
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
          "--icon-url": `url(/framer/icons/${icons[name]}.svg)`,
        } as CSSProperties
      }
    />
  );
}

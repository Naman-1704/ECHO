/**
 * The ECHO wordmark with a stacked, fading repeat behind it — a literal echo.
 * This is the one deliberate "bold" moment in the whole design (see frontend README
 * design notes); everywhere else stays quiet by comparison. Pure CSS, no images.
 */
export function EchoWordmark({ size = "hero" }: { size?: "hero" | "compact" }) {
  if (size === "compact") {
    return (
      <span className="font-serif text-xl tracking-tight text-ink" aria-label="Echo">
        Echo
      </span>
    );
  }

  return (
    <div className="relative inline-block select-none" aria-label="Echo">
      <span
        className="absolute inset-0 font-serif text-6xl md:text-7xl text-oxblood/[0.07] translate-x-2 translate-y-2"
        aria-hidden="true"
      >
        ECHO
      </span>
      <span
        className="absolute inset-0 font-serif text-6xl md:text-7xl text-oxblood/[0.13] translate-x-1 translate-y-1"
        aria-hidden="true"
      >
        ECHO
      </span>
      <span className="relative font-serif text-6xl md:text-7xl text-ink tracking-tight">
        ECHO
      </span>
    </div>
  );
}

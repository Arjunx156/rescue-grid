/** A grid of streets with one point found: the mark. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M3 8h18M3 16h18M8 3v18M16 3v18" stroke="currentColor" strokeOpacity=".45" strokeWidth="1.5" />
      <circle cx="16" cy="8" r="3.2" fill="currentColor" />
      <circle cx="16" cy="8" r="5.6" stroke="currentColor" strokeWidth="1.2" strokeOpacity=".6" />
    </svg>
  );
}

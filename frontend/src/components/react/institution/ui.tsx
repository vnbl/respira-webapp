// Shared presentational pieces for the institutional dashboard (RES-328).
//
// The public site's atoms live in `.astro` files and cannot be used inside a
// React island, so these mirror them in JSX: same palette tokens, same radii,
// same uppercase-label treatment. They stay local to `institution/` rather than
// being promoted to a shared UI folder until something outside this feature
// needs them.

import type { ReactNode } from "react";

// --- Card -------------------------------------------------------------------

/**
 * A panel surface.
 *
 * `tone` is the card's rank on the page, not a colour: every surface stays
 * white, and what separates them is padding and border weight. A dashboard
 * where nine cards are drawn identically gives the eye no order to read them
 * in, and the AQI of the day ends up carrying the same weight as the contact
 * footer.
 *
 * - `main` — the sections the panel exists for. More air, and a slightly
 *   stronger edge, so they read as the primary blocks.
 * - `plain` — the default: everything else.
 * - `quiet` — supporting matter (the contact details). Sits on the page
 *   without asking to be read first.
 */
type CardTone = "main" | "plain" | "quiet";

const CARD_TONE: Record<CardTone, string> = {
  main: "gap-5 p-6 border-basedark/60",
  plain: "gap-4 p-5 border-bg-gray",
  quiet: "gap-3 p-5 border-bg-gray",
};

export function Card({
  children,
  tone = "plain",
  className = "",
}: {
  children: ReactNode;
  tone?: CardTone;
  className?: string;
}) {
  return (
    <section
      className={`flex flex-col rounded-xl border bg-white ${CARD_TONE[tone]} ${className}`}
    >
      {children}
    </section>
  );
}

export function CardHead({ children }: { children: ReactNode }) {
  return <div className="flex items-center gap-3">{children}</div>;
}

/**
 * A section heading.
 *
 * `level` mirrors `Card`'s tone. The uppercase micro-label is right for a
 * supporting card but too quiet for a section someone is meant to land on, so
 * the main ones get the serif face the page's own title uses — the same
 * distinction the AQI panel already makes with `category_label`.
 */
export function CardTitle({
  children,
  level = "section",
}: {
  children: ReactNode;
  level?: "main" | "section";
}) {
  if (level === "main") {
    return <h2 className="m-0 font-serif text-lg font-bold">{children}</h2>;
  }
  return (
    <h2 className="m-0 text-xs font-bold uppercase tracking-[0.1em] text-gray">
      {children}
    </h2>
  );
}

// --- Pill -------------------------------------------------------------------

type PillTone = "on" | "off" | "neutral";

const PILL_TONE: Record<PillTone, string> = {
  on: "bg-light_green text-green_darker",
  // The AQI red at text contrast: dark ink on the light step, not white on it.
  off: "bg-aqi-red-light text-near_black",
  neutral: "bg-base text-gray",
};

export function Pill({
  tone = "neutral",
  dot = false,
  children,
}: {
  tone?: PillTone;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-wider ${PILL_TONE[tone]}`}
    >
      {dot && (
        <span
          aria-hidden="true"
          className="block h-[7px] w-[7px] rounded-full bg-current"
        />
      )}
      {children}
    </span>
  );
}

// --- Buttons ----------------------------------------------------------------

type ButtonProps = {
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  variant?: "color" | "void";
  disabled?: boolean;
  block?: boolean;
};

export function Button({
  children,
  onClick,
  type = "button",
  variant = "color",
  disabled = false,
  block = false,
}: ButtonProps) {
  // `green_dark` rather than the brand `green`: the config notes only the dark
  // greens reach text contrast, and these buttons carry white text.
  const tone =
    variant === "color"
      ? "bg-green_dark text-white hover:bg-green_darker border border-transparent"
      : "border border-basedark text-near_black hover:border-near_black";

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-md px-5 py-3 text-[13px] font-bold uppercase tracking-wide transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green_dark disabled:cursor-not-allowed disabled:opacity-60 ${tone} ${
        block ? "w-full" : ""
      }`}
    >
      {children}
    </button>
  );
}

// --- States -----------------------------------------------------------------

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`block animate-pulse rounded bg-bg-gray motion-reduce:animate-none ${className}`}
    />
  );
}

/**
 * Placeholder that keeps a card's height while its data loads, so the grid does
 * not reflow when the real content arrives.
 */
export function CardSkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <Card>
      <Skeleton className="h-3 w-2/5" />
      <Skeleton className="h-10 w-3/5" />
      {/* Ragged widths read as lines of text rather than as a progress bar. */}
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          className={index % 2 === 0 ? "h-3 w-full" : "h-3 w-4/5"}
        />
      ))}
      <span className="sr-only">Cargando…</span>
    </Card>
  );
}

export function StateBlock({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-2 py-2">
      <p className="font-serif text-[15px] font-bold">{title}</p>
      {body && <p className="text-[13px] text-gray">{body}</p>}
      {action}
    </div>
  );
}

export function ErrorState({
  title,
  body,
  onRetry,
  retryLabel,
}: {
  title: string;
  body: string;
  onRetry?: () => void;
  retryLabel: string;
}) {
  return (
    <div role="alert">
      <StateBlock
        title={title}
        body={body}
        action={
          onRetry ? (
            <Button variant="void" onClick={onRetry}>
              {retryLabel}
            </Button>
          ) : undefined
        }
      />
    </div>
  );
}

// --- Field --------------------------------------------------------------

export const fieldClassName =
  "w-full rounded-md border border-basedark bg-white px-3 py-2 text-sm text-near_black focus-visible:border-green_dark focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-green_dark";

export function FieldLabel({
  htmlFor,
  children,
}: {
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <label htmlFor={htmlFor} className="text-xs font-semibold text-gray">
      {children}
    </label>
  );
}

/**
 * A `<select>` with the panel's own chevron.
 *
 * `appearance-none` drops the platform arrow, which is what makes a native
 * select look like a different control on every OS, and the chevron is drawn
 * over it instead. The element itself stays a real `<select>`, so keyboard
 * behaviour, the mobile wheel picker and screen-reader semantics are the
 * browser's rather than something reimplemented here.
 */
export function Select({
  id,
  value,
  onChange,
  children,
  disabled = false,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <div className="relative">
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className={`${fieldClassName} cursor-pointer appearance-none pr-9 font-semibold disabled:cursor-not-allowed disabled:opacity-60`}
      >
        {children}
      </select>
      <svg
        aria-hidden="true"
        viewBox="0 0 16 16"
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray"
      >
        <path
          d="M4 6.5 8 10.5 12 6.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export function DownloadIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3v12" />
      <path d="m7 11 5 5 5-5" />
      <path d="M4 20h16" />
    </svg>
  );
}

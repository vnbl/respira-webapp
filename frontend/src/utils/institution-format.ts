// Date and number formatting for the institutional dashboard (RES-328).
//
// Every formatter pins the time zone to Asunción. Two reasons, both load-
// bearing: the backend stores timestamps in UTC while institutions read them in
// local time, and these components hydrate — a server rendering in UTC and a
// browser rendering in local time would produce different markup for the same
// data and trip a hydration mismatch.

const TIME_ZONE = "America/Asuncion";
const LOCALE = "es-PY";

const dateTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const shortDateFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  day: "2-digit",
  month: "2-digit",
});

const timeFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const monthFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TIME_ZONE,
  month: "short",
});

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

const parse = (value: string | null | undefined): Date | undefined => {
  if (!value) return undefined;
  // A date-only string (`end_date`, a history point) is a calendar date, not a
  // moment: `new Date("2026-12-31")` reads it as UTC midnight, which is still
  // the 30th in Asunción and prints the wrong day. Anything with a time in it
  // really is an instant and is parsed as one.
  const date = DATE_ONLY.test(value) ? parseApiDate(value) : new Date(value);
  return Number.isNaN(date.getTime()) ? undefined : date;
};

const format =
  (formatter: Intl.DateTimeFormat) =>
  (value: string | null | undefined, fallback = "—"): string => {
    const date = parse(value);
    return date ? formatter.format(date) : fallback;
  };

/** `24/08/2026 08:15` — for a precise moment, like the last measurement. */
export const formatDateTime = format(dateTimeFormatter);

/** `24/08/2026` — for calendar dates, like a contract end. */
export const formatDate = format(dateFormatter);

/** `24/08` — for dense lists where the year is implied. */
export const formatShortDate = format(shortDateFormatter);

/** `08:15` — the time half of a timestamp already labelled with its date. */
export const formatTime = format(timeFormatter);

/** `ago.` — axis ticks on the history chart. */
export const formatMonth = (date: Date): string => monthFormatter.format(date);

const MONTH_LOCALE: Record<string, string> = {
  es: "es-PY",
  en: "en-GB",
  pt: "pt-BR",
};

/**
 * A `YYYY-MM` month, named in the reader's own language.
 *
 * The API labels months in Spanish — it serves the PDF, which is Spanish
 * whatever the panel is set to. In the interface the month is read as a word,
 * so a Spanish label inside an English sentence reads as a bug; the string is
 * rebuilt here instead. Falls back to whatever the API sent if the value is not
 * a month, so a format change degrades to the server's wording rather than to
 * an empty control.
 */
export const formatMonthName = (
  month: string,
  lang: string,
  fallback: string,
): string => {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return fallback;
  const [, year, monthNumber] = match;
  // Day 1 at noon, like `parseApiDate`: far from either day boundary.
  const date = new Date(Number(year), Number(monthNumber) - 1, 1, 12, 0, 0);
  const formatted = new Intl.DateTimeFormat(MONTH_LOCALE[lang] ?? LOCALE, {
    month: "long",
    year: "numeric",
  }).format(date);
  // Spanish and Portuguese give "agosto de 2026" lowercase; sentence case reads
  // better as a standalone label in a control.
  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
};

/**
 * A `YYYY-MM-DD` API date as a Date at local noon.
 *
 * Parsing that string with `new Date()` reads it as UTC midnight, which is the
 * *previous* day in Asunción (UTC−3/−4) and shifts every point on the chart by
 * one day. Noon is far enough from either boundary to be safe.
 */
export const parseApiDate = (value: string): Date => {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return new Date(value);
  return new Date(year, month - 1, day, 12, 0, 0);
};

const integerFormatter = new Intl.NumberFormat(LOCALE, {
  maximumFractionDigits: 0,
});

/** AQI is reported to institutions as a whole number, like everywhere else. */
export const formatAqi = (value: number): string =>
  integerFormatter.format(Math.round(value));

export const formatCoordinates = (
  latitude: number | null,
  longitude: number | null,
): string | undefined => {
  if (latitude == null || longitude == null) return undefined;
  return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
};

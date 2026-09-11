// API client for the institutional dashboard (RES-328).
//
// Two callers with different constraints share this module:
//
//   * Astro pages, rendering on the server. They have no cookie jar, so they
//     forward the visitor's `Cookie` header explicitly and talk to the backend
//     over the internal URL (`getBackendUrl()` resolves that in SSR).
//   * React islands, running in the browser. `BACKEND_URL` is same-origin
//     (`/api` behind nginx), so the session cookie rides along on its own and
//     unsafe methods carry the CSRF token Django set at login.
//
// Every failure is normalised to `InstitutionApiError` with a `code`, so the UI
// can tell "you are logged out" from "this feature does not exist yet" from
// "the network is down" without re-reading status codes at each call site.

import {
  INSTITUTION_ENDPOINTS,
  type ActionLog,
  type ActionLogDraft,
  type Institution,
  type InstitutionAlert,
  type InstitutionDashboard,
  type InstitutionNotification,
  type Paginated,
} from "../data/institution";
import { getBackendUrl } from "./runtime-config";

export type InstitutionApiErrorCode =
  /** No session, or the session expired. The caller should send the user to login. */
  | "unauthenticated"
  /** Authenticated, but the account has no institution linked. */
  | "forbidden"
  /** The institution has no sensor assigned yet (the dashboard endpoint's 404). */
  | "not_found"
  /** The endpoint is not deployed yet — see the unimplemented paths in `data/institution.ts`. */
  | "unavailable"
  /** The request itself was rejected (validation). `fieldErrors` carries the detail. */
  | "invalid"
  /** Anything else: 5xx, a network failure, a timeout, a malformed body. */
  | "unexpected";

export class InstitutionApiError extends Error {
  readonly code: InstitutionApiErrorCode;
  readonly status: number;
  readonly fieldErrors: Record<string, string[]>;

  constructor(
    code: InstitutionApiErrorCode,
    status: number,
    message: string,
    fieldErrors: Record<string, string[]> = {},
  ) {
    super(message);
    this.name = "InstitutionApiError";
    this.code = code;
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

// Long enough for a cold Django worker, short enough that a hung backend does
// not hold an SSR render (and the visitor's page) open indefinitely.
const REQUEST_TIMEOUT_MS = 10_000;

const codeForStatus = (status: number): InstitutionApiErrorCode => {
  if (status === 401) return "unauthenticated";
  // DRF answers an unauthenticated SessionAuthentication request with 403, so
  // 403 alone cannot distinguish "logged out" from "no institution linked".
  // Callers that need to tell them apart use `isLoggedOut` below.
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 400) return "invalid";
  return "unexpected";
};

/**
 * True when a 403 most likely means "no session" rather than "no institution".
 *
 * DRF collapses both onto 403 under SessionAuthentication. The difference shows
 * in the body: the permission classes carry their own `message`, while the
 * unauthenticated case falls back to DRF's default string.
 */
const isLoggedOutDetail = (detail: string): boolean =>
  detail.toLowerCase().includes("credentials were not provided");

type ErrorBody = {
  detail?: unknown;
  [key: string]: unknown;
};

const parseErrorBody = async (
  response: Response,
): Promise<{ detail: string; fieldErrors: Record<string, string[]> }> => {
  let body: ErrorBody | undefined;
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    return { detail: "", fieldErrors: {} };
  }

  if (!body || typeof body !== "object") {
    return { detail: "", fieldErrors: {} };
  }

  const detail = typeof body.detail === "string" ? body.detail : "";

  const fieldErrors: Record<string, string[]> = {};
  for (const [key, value] of Object.entries(body)) {
    if (key === "detail") continue;
    if (Array.isArray(value)) {
      const messages = value.filter(
        (item): item is string => typeof item === "string",
      );
      if (messages.length) fieldErrors[key] = messages;
    } else if (typeof value === "string") {
      fieldErrors[key] = [value];
    }
  }

  return { detail, fieldErrors };
};

const raiseForResponse = async (
  response: Response,
  /** Paths that are not deployed yet report 404 as `unavailable`, not `not_found`. */
  treat404AsUnavailable: boolean,
): Promise<never> => {
  const { detail, fieldErrors } = await parseErrorBody(response);
  let code = codeForStatus(response.status);

  if (code === "forbidden" && isLoggedOutDetail(detail)) {
    code = "unauthenticated";
  }
  if (code === "not_found" && treat404AsUnavailable) {
    code = "unavailable";
  }

  throw new InstitutionApiError(
    code,
    response.status,
    detail || `Request failed with status ${response.status}`,
    fieldErrors,
  );
};

// --- CSRF -------------------------------------------------------------------

const CSRF_COOKIE = "csrftoken";

/**
 * Reads Django's CSRF cookie.
 *
 * `CSRF_COOKIE_HTTPONLY` is left at its default (false) in
 * `backend/backend/settings.py`, which is what makes this readable — the token
 * is set on the login response by the view's explicit `get_token(request)`.
 */
export const getCsrfToken = (): string => {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${CSRF_COOKIE}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : "";
};

// --- Request plumbing -------------------------------------------------------

type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
  /** Forwarded by SSR callers; the browser sends cookies on its own. */
  cookie?: string;
  treat404AsUnavailable?: boolean;
  signal?: AbortSignal;
};

const request = async (
  path: string,
  options: RequestOptions = {},
): Promise<Response> => {
  const {
    method = "GET",
    body,
    cookie,
    treat404AsUnavailable = false,
    signal,
  } = options;

  const backendUrl = await getBackendUrl();
  const headers: Record<string, string> = { Accept: "application/json" };

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (cookie) {
    headers["Cookie"] = cookie;
  }
  if (method !== "GET" && typeof document !== "undefined") {
    const token = getCsrfToken();
    if (token) headers["X-CSRFToken"] = token;
  }

  let response: Response;
  try {
    response = await fetch(`${backendUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      // Same-origin in every deployment (`BACKEND_URL=/api`); `include` also
      // covers a cross-origin backend without changing same-origin behaviour.
      credentials: "include",
      cache: "no-store",
      signal: signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    // A network failure, an abort, or a DNS error — never an HTTP status.
    throw new InstitutionApiError(
      "unexpected",
      0,
      error instanceof Error ? error.message : "Network request failed",
    );
  }

  if (!response.ok) {
    await raiseForResponse(response, treat404AsUnavailable);
  }
  return response;
};

const requestJson = async <T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> => {
  const response = await request(path, options);
  try {
    return (await response.json()) as T;
  } catch {
    throw new InstitutionApiError(
      "unexpected",
      response.status,
      "The server returned a response that is not valid JSON.",
    );
  }
};

// --- Session ----------------------------------------------------------------

/** Signs in and returns the caller's own institution. Browser-only. */
export const login = (email: string, password: string): Promise<Institution> =>
  requestJson<Institution>(INSTITUTION_ENDPOINTS.login, {
    method: "POST",
    body: { email, password },
  });

/**
 * Asks for a password reset email.
 *
 * Resolves for any well-formed address, registered or not — the backend answers
 * the same way either way on purpose (account enumeration), so a caller has no
 * way to tell, and the UI must not pretend otherwise.
 */
export const requestPasswordReset = async (email: string): Promise<void> => {
  await request(INSTITUTION_ENDPOINTS.passwordReset, {
    method: "POST",
    body: { email },
  });
};

/**
 * Sets a new password from an emailed reset link.
 *
 * Rejects with `code: "invalid"` in two distinguishable cases: the link is
 * unusable (expired, tampered with, already spent), which surfaces under
 * `non_field_errors`, or the password does not meet the platform's rules,
 * which surfaces under `new_password`.
 */
export const confirmPasswordReset = async (
  uid: string,
  token: string,
  newPassword: string,
): Promise<void> => {
  await request(INSTITUTION_ENDPOINTS.passwordResetConfirm, {
    method: "POST",
    body: { uid, token, new_password: newPassword },
  });
};

/** Ends the session. Resolves even if the session was already gone. */
export const logout = async (): Promise<void> => {
  try {
    await request(INSTITUTION_ENDPOINTS.logout, { method: "POST" });
  } catch (error) {
    if (
      error instanceof InstitutionApiError &&
      (error.code === "unauthenticated" || error.code === "forbidden")
    ) {
      return;
    }
    throw error;
  }
};

// --- Reads ------------------------------------------------------------------

export const fetchInstitution = (cookie?: string): Promise<Institution> =>
  requestJson<Institution>(INSTITUTION_ENDPOINTS.me, { cookie });

export const fetchDashboard = (
  cookie?: string,
): Promise<InstitutionDashboard> =>
  requestJson<InstitutionDashboard>(INSTITUTION_ENDPOINTS.dashboard, {
    cookie,
  });

export const fetchActionLogs = (
  page = 1,
  cookie?: string,
): Promise<Paginated<ActionLog>> =>
  requestJson<Paginated<ActionLog>>(
    `${INSTITUTION_ENDPOINTS.actionLogs}?page=${page}`,
    { cookie, treat404AsUnavailable: true },
  );

/**
 * The alerts an action may be linked to.
 *
 * Only the first page: the selector offers recent events to respond to, and an
 * institution reaching for one from twenty alerts ago is not the case this is
 * for. The endpoint may answer unpaginated, so both shapes are accepted.
 */
export const fetchInstitutionAlerts = async (
  cookie?: string,
): Promise<InstitutionAlert[]> => {
  const payload = await requestJson<
    Paginated<InstitutionAlert> | InstitutionAlert[]
  >(INSTITUTION_ENDPOINTS.alerts, { cookie, treat404AsUnavailable: true });

  return Array.isArray(payload) ? payload : payload.results;
};

/**
 * The notifications sent about the institution's sensor, newest first.
 *
 * Both response shapes are accepted, like `fetchInstitutionAlerts`: the
 * endpoint is a router action on a viewset that sets no `pagination_class`, so
 * today it answers a plain array and only starts wrapping results in a page
 * object if one is configured later. Normalised here so the panel's paging
 * logic has one shape to read either way.
 */
export const fetchInstitutionNotifications = async (
  page = 1,
  cookie?: string,
): Promise<Paginated<InstitutionNotification>> => {
  const payload = await requestJson<
    Paginated<InstitutionNotification> | InstitutionNotification[]
  >(`${INSTITUTION_ENDPOINTS.notifications}?page=${page}`, {
    cookie,
    treat404AsUnavailable: true,
  });

  return Array.isArray(payload)
    ? { count: payload.length, next: null, previous: null, results: payload }
    : payload;
};

export const createActionLog = (draft: ActionLogDraft): Promise<ActionLog> =>
  requestJson<ActionLog>(INSTITUTION_ENDPOINTS.actionLogs, {
    method: "POST",
    body: {
      station: draft.station,
      note: draft.note,
      // Omit the key entirely when there is no alert: the field is nullable,
      // and sending `undefined` would serialise to nothing anyway.
      ...(draft.alert == null ? {} : { alert: draft.alert }),
    },
    treat404AsUnavailable: true,
  });

// --- Downloads --------------------------------------------------------------

export type DownloadKind = "monthlyReport" | "rawExport";

/**
 * Fetches a file and hands it to the browser as a download.
 *
 * Goes through `fetch` rather than a plain link so a 401/403/404 surfaces as an
 * error in the UI instead of navigating the visitor to a JSON error page.
 */
export type DownloadOutcome = {
  /**
   * How many sub-ranges the sensor API failed to serve, from
   * `X-Respira-Partial-Export`. Zero for a complete file. The raw export is
   * fetched live and window by window, so it can succeed with gaps — the file
   * is still worth handing over, but the caller has to be able to say so.
   */
  missingRanges: number;
};

export type ReportMonth = { month: string; label: string };

/**
 * The months the institution actually has readings for, plus the one to
 * preselect. Drives the report's month selector: offering every month since the
 * contract began would let a visitor pick one that yields an empty report.
 */
export const fetchReportMonths = async (
  cookie?: string,
): Promise<{ months: ReportMonth[]; default: string | null }> =>
  requestJson<{ months: ReportMonth[]; default: string | null }>(
    INSTITUTION_ENDPOINTS.reportMonths,
    { cookie, treat404AsUnavailable: true },
  );

export const downloadInstitutionFile = async (
  kind: DownloadKind,
  options: { month?: string } = {},
): Promise<DownloadOutcome> => {
  const endpoint = options.month
    ? `${INSTITUTION_ENDPOINTS[kind]}?month=${encodeURIComponent(options.month)}`
    : INSTITUTION_ENDPOINTS[kind];
  const response = await request(endpoint, {
    treat404AsUnavailable: true,
  });

  const missingRanges = Number(
    response.headers.get("X-Respira-Partial-Export") ?? 0,
  );

  const blob = await response.blob();
  const filename = filenameFromResponse(response, kind);

  // `msSaveOrOpenBlob` is the only path that works in embedded WebViews which
  // block navigation to blob: URLs (VS Code's Simple Browser among them); the
  // anchor click below silently does nothing there.
  const legacySave = (
    navigator as Navigator & {
      msSaveOrOpenBlob?: (blob: Blob, filename: string) => boolean;
    }
  ).msSaveOrOpenBlob;
  if (typeof legacySave === "function") {
    legacySave.call(navigator, blob, filename);
    return {
      missingRanges: Number.isFinite(missingRanges) ? missingRanges : 0,
    };
  }

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  // `rel=noopener` matters for the fallback below, where a blocked download can
  // fall back to opening the blob in a tab.
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoking in the same tick can invalidate the URL before the browser has
  // started reading it — the download then fails silently, with no error to
  // catch. One minute is far longer than any handoff needs and still bounds the
  // memory the blob holds.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);

  return { missingRanges: Number.isFinite(missingRanges) ? missingRanges : 0 };
};

const FALLBACK_FILENAME: Record<DownloadKind, string> = {
  monthlyReport: "reporte-mensual.pdf",
  rawExport: "historial-mediciones.xlsx",
};

const filenameFromResponse = (
  response: Response,
  kind: DownloadKind,
): string => {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  // Prefer RFC 5987 (`filename*=UTF-8''…`) when present; fall back to the plain
  // `filename="…"` form, and to a sensible default when the header is absent.
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      // Malformed percent-encoding: fall through to the plain form.
    }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i);
  if (plain) return plain[1];
  return FALLBACK_FILENAME[kind];
};

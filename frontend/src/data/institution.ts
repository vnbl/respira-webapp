// Shapes and constants for the institutional dashboard (RES-328).
//
// The types mirror the DRF serializers in `backend/api/serializers.py` field by
// field. They are written by hand rather than generated because the frontend
// consumes a handful of endpoints, not the whole schema — but they must be kept
// in step with those serializers when the backend changes.

/** Paths under the API root (`BACKEND_URL`, e.g. `/api`). */
export const INSTITUTION_ENDPOINTS = {
  // Implemented: RES-368 (auth) and RES-369 (dashboard).
  login: "/institution/login/",
  logout: "/institution/logout/",
  me: "/institution/me/",
  dashboard: "/institution/dashboard/",

  // Password recovery. Both are open (no session, by definition) and answer
  // 204; `passwordReset` answers 204 even for an address that is not
  // registered, so the UI must never treat its response as confirmation that
  // an account exists.
  passwordReset: "/institution/password-reset/",
  passwordResetConfirm: "/institution/password-reset/confirm/",

  // Implemented in RES-370. Note it is registered at the API root
  // (`/action-logs/`), not nested under `/institution/`: the router entry is
  // `router.register(r"action-logs", ActionLogViewSet, ...)`. The institution is
  // resolved from the session, so no id ever travels in the path.
  actionLogs: "/action-logs/",

  // The events an action can respond to. Read-only: alerts are produced by the
  // platform, never authored by an institution.
  alerts: "/institution/alerts/",

  // What the platform sent *about* the sensor, as opposed to what the
  // institution did about it. Merges the AQI-triggered alerts and the manual
  // announcements server-side, so this is one paginated, ordered feed.
  notifications: "/institution/notifications/",

  monthlyReport: "/institution/report/monthly/",
  rawExport: "/institution/export/",
} as const;

// --- Institution ------------------------------------------------------------

export type ContractStatus = "draft" | "active" | "expired" | "cancelled";

export type InstitutionContract = {
  id: number;
  station: number;
  station_name: string;
  contract_status: ContractStatus;
  start_date: string;
  end_date: string | null;
  monthly_fee: string | null;
  signed_contract_url: string;
};

export type Institution = {
  id: number;
  legal_name: string;
  display_name: string;
  institution_type: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  address: string;
  city: string;
  contract: InstitutionContract | null;
};

/** The name to show in the top bar: `display_name` is optional in the model. */
export const institutionName = (institution: Institution): string =>
  institution.display_name || institution.legal_name;

// --- Dashboard --------------------------------------------------------------

export type DashboardLocation = {
  city: string | null;
  specific_location: string | null;
  latitude: number | null;
  longitude: number | null;
};

export type DashboardSensor = {
  id: number;
  name: string;
  status: "online" | "offline";
  location: DashboardLocation;
  last_measurement_at: string | null;
};

export type DashboardAirQuality = {
  aqi: number;
  category: string;
  category_label: string;
  message: string;
  recommendations: string[];
};

export type DashboardHistoryPoint = {
  date: string;
  /** Null on days the sensor reported nothing — the chart must skip these. */
  aqi: number | null;
};

export type SensitiveGroup = {
  key: string;
  label: string;
  emoji: string;
};

export type InstitutionAlertConfig = {
  is_enabled: boolean;
  alert_threshold: number | null;
  sensitive_groups: SensitiveGroup[];
};

export type InstitutionDashboard = {
  sensor: DashboardSensor;
  /** Null until the sensor reports its first measurement. */
  air_quality: DashboardAirQuality | null;
  history: DashboardHistoryPoint[];
  alert_config: InstitutionAlertConfig;
};

// --- Action log -------------------------------------------------------------

/** An air-quality event the platform recorded for the institution's sensor. */
export type InstitutionAlert = {
  id: number;
  station: number;
  station_name: string;
  aqi_value: number;
  /** The threshold in force when it fired, copied so later edits don't rewrite history. */
  alert_threshold: number | null;
  triggered_at: string;
  resolved_at: string | null;
  is_resolved: boolean;
};

export type ActionLog = {
  id: number;
  institution: number;
  institution_name: string;
  station: number;
  station_name: string;
  /** The alert this action responded to, when it responded to one. */
  alert: number | null;
  /** The same alert expanded, so a list can be rendered without a second request. */
  alert_detail: InstitutionAlert | null;
  /** Server-assigned (`auto_now_add`); never sent by the client. */
  timestamp: string;
  note: string;
};

/**
 * What the client may send on create.
 *
 * `institution` and `timestamp` are deliberately absent: the viewset assigns
 * them from the session and rejects client-supplied values.
 */
export type ActionLogDraft = {
  station: number;
  note: string;
  alert?: number | null;
};

// --- Sensor notifications ---------------------------------------------------

/** Which feed a notification came from; see `InstitutionNotification`. */
export type NotificationType = "aqi" | "general";

/**
 * One notification the platform sent about the institution's sensor.
 *
 * Mirrors `InstitutionNotificationSerializer`, which normalises two backend
 * models into this one shape: `InstitutionAlert` for the AQI-triggered ones and
 * `PushBroadcast` for the manual announcements.
 *
 * Everything AQI-specific is nullable, because a manual announcement has no
 * reading behind it. Read `type` rather than testing those fields for presence.
 */
export type InstitutionNotification = {
  /** Prefixed by source (`"alert-12"`, `"broadcast-7"`): the two tables number rows independently. */
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  sent_at: string;
  /** Null on an institution-wide announcement, which names no single station. */
  station: number | null;
  station_name: string | null;
  /** Null on every general notification. */
  aqi: number | null;
  /** A key of `CATEGORY_EMOJI` / `AQI_LEVELS`, e.g. `"unhealthy"`. */
  aqi_category: string | null;
  aqi_category_label: string | null;
  alert_threshold: number | null;
  /** The `InstitutionAlert` behind it, so it can be tied to an action's alert. */
  alert: number | null;
};

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

/** Matches `note = models.TextField()` with the serializer's non-empty check. */
export const ACTION_NOTE_MAX_LENGTH = 1000;

// --- AQI categories ---------------------------------------------------------

// `air_quality.category` arrives in the snake_case keys of `backend/api/aqi.py`.
// The band colour itself comes from `getColorRange(aqi)` — the same table the
// public map uses — so a value is never a different colour here than there.
// Only the emoji has no numeric source, so it is mapped by category.

/** Mirrors the `emoji` field of `AQI_LEVELS` in `backend/api/aqi.py`. */
const CATEGORY_EMOJI: Record<string, string> = {
  good: "😁",
  moderate: "🙂",
  unhealthy_sensitive: "😷",
  unhealthy: "😶‍🌫️",
  very_unhealthy: "😨",
  hazardous: "💀",
};

export const emojiForCategory = (category: string): string =>
  CATEGORY_EMOJI[category] ?? "";

import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import {
  ACTION_NOTE_MAX_LENGTH,
  type ActionLog,
  type InstitutionAlert,
} from "../../../data/institution";
import type { Lang } from "../../../i18n/config";
import { useInstitutionCopy } from "../../../i18n/institution";
import {
  InstitutionApiError,
  createActionLog,
  fetchActionLogs,
  fetchInstitutionAlerts,
} from "../../../store/institution";
import {
  formatAqi,
  formatShortDate,
  formatTime,
} from "../../../utils/institution-format";
import { INSTITUTION_LOGIN_PATH } from "../../../utils/institution-session";
import {
  Button,
  Card,
  CardHead,
  CardTitle,
  ErrorState,
  FieldLabel,
  Pill,
  Skeleton,
  StateBlock,
  fieldClassName,
} from "./ui";

// Loaded in the browser rather than during SSR: the list is paginated and
// changes as the visitor adds to it, so it owns its own state from the start.
type ListState =
  | { status: "loading" }
  | { status: "ready"; items: ActionLog[]; hasMore: boolean; page: number }
  | { status: "error" }
  | { status: "expired" }
  /** RES-370 is not deployed yet — `/action-logs/` answers 404. */
  | { status: "unavailable" };

const stateForError = (error: unknown): ListState => {
  if (error instanceof InstitutionApiError) {
    if (error.code === "unavailable") return { status: "unavailable" };
    if (error.code === "unauthenticated") return { status: "expired" };
  }
  return { status: "error" };
};

export function ActionLogPanel({
  stationId,
  stationName,
  lang,
}: {
  /** The institution's own station; the form has nothing to choose between. */
  stationId: number | null;
  stationName: string;
  lang: Lang;
}) {
  // No `copy` here: this component renders no text of its own, it just passes
  // `lang` down to the list and the form, which each resolve their own.
  const [list, setList] = useState<ListState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  // Alerts are optional context for the form, so a failure to load them is not
  // an error state: the selector simply offers nothing and a note can still be
  // saved without one.
  const [alerts, setAlerts] = useState<InstitutionAlert[]>([]);

  const load = useCallback(async () => {
    setList({ status: "loading" });
    try {
      const page = await fetchActionLogs(1);
      setList({
        status: "ready",
        items: page.results,
        hasMore: Boolean(page.next),
        page: 1,
      });
    } catch (error) {
      setList(stateForError(error));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    fetchInstitutionAlerts()
      .then(setAlerts)
      .catch((error) => {
        console.error("Could not load the institution's alerts", error);
      });
  }, []);

  const loadMore = async () => {
    if (list.status !== "ready" || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await fetchActionLogs(list.page + 1);
      setList({
        status: "ready",
        items: [...list.items, ...next.results],
        hasMore: Boolean(next.next),
        page: list.page + 1,
      });
    } catch (error) {
      setList(stateForError(error));
    } finally {
      setLoadingMore(false);
    }
  };

  // A new entry goes straight to the top of the list the visitor is looking at,
  // which is also where the API would put it (`-timestamp, -id`).
  const prepend = (created: ActionLog) => {
    setList((current) =>
      current.status === "ready"
        ? { ...current, items: [created, ...current.items] }
        : current,
    );
  };

  return (
    <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-12">
      {/* `items-start`, not stretched: forcing both cards to one height means a
          history with two entries is padded out to the height of a six-field
          form, and the empty half reads as something failing to load. Each card
          takes the height its content needs; the shared top edge is what makes
          them a pair. */}
      <div className="lg:col-span-7">
        <ActionLogList
          state={list}
          onRetry={load}
          onLoadMore={loadMore}
          loadingMore={loadingMore}
          lang={lang}
        />
      </div>
      <div className="lg:col-span-5">
        <ActionLogForm
          stationId={stationId}
          stationName={stationName}
          alerts={alerts}
          disabled={list.status === "unavailable"}
          onCreated={prepend}
          lang={lang}
        />
      </div>
    </div>
  );
}

// --- List -------------------------------------------------------------------

function ActionLogList({
  state,
  onRetry,
  onLoadMore,
  loadingMore,
  lang,
}: {
  state: ListState;
  onRetry: () => void;
  onLoadMore: () => void;
  loadingMore: boolean;
  lang: Lang;
}) {
  const copy = useInstitutionCopy(lang);
  return (
    <Card tone="main">
      <CardHead>
        <CardTitle level="main">{copy.actionsTitle}</CardTitle>
        {state.status === "ready" && state.items.length > 0 && (
          <span className="ml-auto">
            <Pill>{state.items.length}</Pill>
          </span>
        )}
      </CardHead>

      {state.status === "loading" && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
          <Skeleton className="h-3 w-3/5" />
          <span className="sr-only">{copy.loading}</span>
        </div>
      )}

      {state.status === "error" && (
        <ErrorState
          title={copy.errorTitle}
          body={copy.errorBody}
          onRetry={onRetry}
          retryLabel={copy.retry}
        />
      )}

      {state.status === "expired" && (
        <StateBlock
          title={copy.sessionExpiredTitle}
          body={copy.sessionExpiredBody}
          action={
            <Button
              variant="void"
              onClick={() => window.location.assign(INSTITUTION_LOGIN_PATH)}
            >
              {copy.goToLogin}
            </Button>
          }
        />
      )}

      {state.status === "unavailable" && (
        <StateBlock
          title={copy.actionsUnavailableTitle}
          body={copy.actionsUnavailableBody}
        />
      )}

      {state.status === "ready" &&
        (state.items.length === 0 ? (
          <StateBlock
            title={copy.actionsEmptyTitle}
            body={copy.actionsEmptyBody}
          />
        ) : (
          /* Capped and scrollable, like the notifications feed: the history
             only grows, and past a point it should not be what decides how tall
             this half of the page is. */
          <div className="-mx-1 max-h-[26rem] overflow-y-auto overscroll-contain px-1">
            <ul className="m-0 flex list-none flex-col p-0">
              {state.items.map((item) => (
                <li
                  key={item.id}
                  className="grid grid-cols-[64px_1fr] gap-3.5 border-b border-bg-gray py-3 last:border-b-0 last:pb-0"
                >
                  <p className="m-0 pt-0.5 text-xs leading-snug text-gray tabular-nums">
                    {formatShortDate(item.timestamp)}
                    <span className="block text-lightgray">
                      {formatTime(item.timestamp)}
                    </span>
                  </p>
                  <div>
                    <p className="m-0 whitespace-pre-line text-[13.5px]">
                      {item.note}
                    </p>
                    {item.alert != null && (
                      <p className="m-0 mt-2 inline-flex items-center gap-1.5 rounded bg-light_green px-2 py-1 text-[11.5px] text-green_darker tabular-nums">
                        <span aria-hidden="true">⚡</span>
                        {item.alert_detail ? (
                          <>
                            {copy.actionsRespondsToAlert}{" "}
                            {formatShortDate(item.alert_detail.triggered_at)} ·{" "}
                            {formatAqi(item.alert_detail.aqi_value)} AQI
                          </>
                        ) : (
                          // The id is there but the expansion is not — an older
                          // payload, or an alert deleted after the fact.
                          copy.actionsRespondsToAlertPlain
                        )}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {state.hasMore && (
              <div className="pt-2">
                <Button
                  variant="void"
                  onClick={onLoadMore}
                  disabled={loadingMore}
                  block
                >
                  {loadingMore ? copy.actionsLoadingMore : copy.actionsLoadMore}
                </Button>
              </div>
            )}
          </div>
        ))}
    </Card>
  );
}

// --- Form -------------------------------------------------------------------

function ActionLogForm({
  stationId,
  stationName,
  alerts,
  disabled,
  onCreated,
  lang,
}: {
  stationId: number | null;
  stationName: string;
  alerts: InstitutionAlert[];
  disabled: boolean;
  onCreated: (created: ActionLog) => void;
  lang: Lang;
}) {
  const copy = useInstitutionCopy(lang);
  const noteId = useId();
  const alertId = useId();
  const [note, setNote] = useState("");
  // "" means no alert. Kept as a string because that is what a <select> value
  // is; it becomes a number only on the way out.
  const [alert, setAlert] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [saved, setSaved] = useState(false);

  // The backend rejects an alert raised on a station other than the one being
  // acted on, so the selector never offers that combination in the first place.
  const selectableAlerts = alerts.filter((item) => item.station === stationId);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting || stationId == null) return;

    const trimmed = note.trim();
    // Mirrors the serializer's own checks so the common mistakes are caught
    // without a round trip; the server stays the authority either way.
    if (!trimmed) {
      setError(copy.actionFormNoteRequired);
      return;
    }
    if (trimmed.length > ACTION_NOTE_MAX_LENGTH) {
      setError(copy.actionFormNoteTooLong);
      return;
    }

    setSubmitting(true);
    setError(undefined);
    setSaved(false);

    try {
      const created = await createActionLog({
        station: stationId,
        note: trimmed,
        alert: alert ? Number(alert) : null,
      });
      onCreated(created);
      setNote("");
      setAlert("");
      setSaved(true);
    } catch (caught) {
      if (caught instanceof InstitutionApiError) {
        if (caught.code === "unauthenticated") {
          window.location.assign(INSTITUTION_LOGIN_PATH);
          return;
        }
        if (caught.code === "unavailable") {
          setError(copy.actionsUnavailableTitle);
        } else {
          // Prefer the server's own field message when it sent one.
          setError(caught.fieldErrors.note?.[0] ?? copy.actionFormError);
        }
      } else {
        setError(copy.actionFormError);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (stationId == null) {
    return (
      <Card tone="main">
        <CardHead>
          <CardTitle level="main">{copy.actionFormTitle}</CardTitle>
        </CardHead>
        <p className="m-0 text-[13px] text-gray">{copy.actionFormNoStation}</p>
      </Card>
    );
  }

  return (
    <Card tone="main">
      <CardHead>
        <CardTitle level="main">{copy.actionFormTitle}</CardTitle>
      </CardHead>

      <form className="flex flex-col gap-4" onSubmit={handleSubmit} noValidate>
        <p className="m-0 flex items-baseline gap-2.5 rounded-md bg-base px-3 py-2 text-[13px]">
          <span className="text-[11px] font-bold uppercase tracking-wider text-gray">
            {copy.actionFormSensor}
          </span>
          <span>{stationName}</span>
        </p>

        {selectableAlerts.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <FieldLabel htmlFor={alertId}>
              {copy.actionFormAlertLabel}{" "}
              <span className="font-normal text-lightgray">
                {copy.actionFormAlertOptional}
              </span>
            </FieldLabel>
            <select
              id={alertId}
              className={fieldClassName}
              value={alert}
              onChange={(event) => setAlert(event.target.value)}
              disabled={disabled || submitting}
            >
              <option value="">{copy.actionFormAlertNone}</option>
              {selectableAlerts.map((item) => (
                <option key={item.id} value={String(item.id)}>
                  {formatShortDate(item.triggered_at)} ·{" "}
                  {formatAqi(item.aqi_value)} AQI
                  {item.alert_threshold == null
                    ? ""
                    : ` (umbral ${item.alert_threshold})`}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <FieldLabel htmlFor={noteId}>{copy.actionFormNoteLabel}</FieldLabel>
          <textarea
            id={noteId}
            className={`${fieldClassName} min-h-[74px] resize-y`}
            value={note}
            maxLength={ACTION_NOTE_MAX_LENGTH}
            placeholder={copy.actionFormNotePlaceholder}
            onChange={(event) => {
              setNote(event.target.value);
              setSaved(false);
            }}
            disabled={disabled || submitting}
            required
          />
          <span className="text-[11.5px] text-lightgray">
            {copy.actionFormNoteHelp}
          </span>
        </div>

        {error && (
          <p role="alert" className="m-0 text-[13px] text-aqi-red-dark">
            {error}
          </p>
        )}
        {saved && (
          <p role="status" className="m-0 text-[13px] text-green_darker">
            {copy.actionFormSaved}
          </p>
        )}

        <Button type="submit" block disabled={disabled || submitting}>
          {submitting ? copy.actionFormSubmitting : copy.actionFormSubmit}
        </Button>
      </form>
    </Card>
  );
}

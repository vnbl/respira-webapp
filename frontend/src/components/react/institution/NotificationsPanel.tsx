import { useCallback, useEffect, useState } from "react";

import {
  emojiForCategory,
  type InstitutionAlertConfig,
  type InstitutionNotification,
} from "../../../data/institution";
import type { Lang } from "../../../i18n/config";
import { useInstitutionCopy } from "../../../i18n/institution";
import {
  InstitutionApiError,
  fetchInstitutionNotifications,
} from "../../../store/institution";
import {
  formatAqi,
  formatShortDate,
  formatTime,
} from "../../../utils/institution-format";
import { INSTITUTION_LOGIN_PATH } from "../../../utils/institution-session";
import { getColorRange, isValidAqi } from "../../../utils";
import {
  Button,
  Card,
  CardHead,
  CardTitle,
  ErrorState,
  Pill,
  Skeleton,
  StateBlock,
} from "./ui";

// Loaded in the browser rather than during SSR, like the action log: the feed
// is paginated and grows on its own, so it owns its state from the start.
type ListState =
  | { status: "loading" }
  | {
      status: "ready";
      items: InstitutionNotification[];
      hasMore: boolean;
      page: number;
      /** Everything the sensor has, not just what is loaded — the badge shows this. */
      total: number;
    }
  | { status: "error" }
  | { status: "expired" }
  /** The endpoint is not deployed yet — `/institution/notifications/` answers 404. */
  | { status: "unavailable" };

const stateForError = (error: unknown): ListState => {
  if (error instanceof InstitutionApiError) {
    if (error.code === "unavailable") return { status: "unavailable" };
    if (error.code === "unauthenticated") return { status: "expired" };
  }
  return { status: "error" };
};

/**
 * What the platform sent *about* the sensor — the mirror of the action log.
 *
 * Read-only by nature: notifications are produced by the scheduled sender or by
 * an operator, so there is nothing for an institution to submit here. That is
 * the whole difference from `ActionLogPanel`, which is a form plus its history;
 * the two sections sit side by side and neither reads the other's data.
 *
 * Carries the alert *configuration* in its header rather than leaving it in a
 * card of its own. Shown separately, the two read as two different channels —
 * "we warn you above 100 AQI" in one box and a list of warnings in another
 * invites the question of whether those are the same warnings. They are: the
 * threshold is the rule, the list is what that rule produced. Stating the rule
 * directly above its own history is what makes that legible.
 *
 * Both kinds of notification share one list. `type` is what separates them —
 * an AQI alert carries a reading and a threshold, a general announcement
 * carries neither — so every AQI-specific field is rendered only when present
 * rather than assumed.
 */
export function NotificationsPanel({
  alertConfig,
  contactMail,
  lang,
}: {
  alertConfig: InstitutionAlertConfig;
  contactMail: string;
  lang: Lang;
}) {
  const copy = useInstitutionCopy(lang);
  const [list, setList] = useState<ListState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);

  const load = useCallback(async () => {
    setList({ status: "loading" });
    try {
      const page = await fetchInstitutionNotifications(1);
      setList({
        status: "ready",
        items: page.results,
        hasMore: Boolean(page.next),
        page: 1,
        total: page.count,
      });
    } catch (error) {
      setList(stateForError(error));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const loadMore = async () => {
    if (list.status !== "ready" || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await fetchInstitutionNotifications(list.page + 1);
      setList({
        status: "ready",
        items: [...list.items, ...next.results],
        hasMore: Boolean(next.next),
        page: list.page + 1,
        total: next.count,
      });
    } catch (error) {
      setList(stateForError(error));
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <Card tone="main">
      <CardHead>
        <CardTitle level="main">{copy.notificationsTitle}</CardTitle>
        {list.status === "ready" && list.items.length > 0 && (
          <span className="ml-auto">
            {/* The sensor's whole history, not the part currently loaded — the
                list is paginated, so those two numbers differ. */}
            <Pill>{list.total}</Pill>
          </span>
        )}
      </CardHead>

      <AlertSettings
        alertConfig={alertConfig}
        contactMail={contactMail}
        lang={lang}
      />

      {list.status === "loading" && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
          <Skeleton className="h-3 w-3/5" />
          <span className="sr-only">{copy.loading}</span>
        </div>
      )}

      {list.status === "error" && (
        <ErrorState
          title={copy.errorTitle}
          body={copy.errorBody}
          onRetry={load}
          retryLabel={copy.retry}
        />
      )}

      {list.status === "expired" && (
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

      {list.status === "unavailable" && (
        <StateBlock
          title={copy.notificationsUnavailableTitle}
          body={copy.notificationsUnavailableBody}
        />
      )}

      {list.status === "ready" &&
        (list.items.length === 0 ? (
          <StateBlock
            title={copy.notificationsEmptyTitle}
            body={copy.notificationsEmptyBody}
          />
        ) : (
          <>
            {/* Scrolls inside the card rather than growing it. A leased sensor
                accumulates notifications indefinitely, and an unbounded list
                pushes the cards below it off the page — the history is worth
                keeping reachable, not worth handing the whole viewport to.
                `max-h` rather than `h`: a short feed still sizes to content
                instead of leaving dead space under it. */}
            <div className="-mx-1 max-h-[28rem] overflow-y-auto overscroll-contain px-1">
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {list.items.map((item) => (
                  <NotificationRow key={item.id} item={item} lang={lang} />
                ))}
              </ul>
              {list.hasMore && (
                <div className="pt-2">
                  <Button
                    variant="void"
                    onClick={loadMore}
                    disabled={loadingMore}
                    block
                  >
                    {loadingMore
                      ? copy.notificationsLoadingMore
                      : copy.notificationsLoadMore}
                  </Button>
                </div>
              )}
            </div>
          </>
        ))}
    </Card>
  );
}

// --- Settings header --------------------------------------------------------

/**
 * The standing rule, stated directly above the history it produced.
 *
 * A band rather than a card: this is context for the list below it, not a
 * section competing with it. Read-only, like the card it replaces — the API
 * exposes no write path for `InstitutionAlertConfig`, so changes go through the
 * team via the contact link.
 */
function AlertSettings({
  alertConfig,
  contactMail,
  lang,
}: {
  alertConfig: InstitutionAlertConfig;
  contactMail: string;
  lang: Lang;
}) {
  const copy = useInstitutionCopy(lang);
  const { is_enabled: enabled, alert_threshold: threshold } = alertConfig;
  const groups = alertConfig.sensitive_groups;

  return (
    <div className="flex flex-col gap-2.5 rounded-lg bg-base px-4 py-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {enabled && threshold != null ? (
          <p className="m-0 text-[13px] text-gray">
            {copy.notificationsRuleLead}{" "}
            <span className="font-serif text-lg font-bold tabular-nums text-near_black">
              {threshold}
            </span>{" "}
            <span className="text-near_black">
              {copy.notificationsRuleUnit}
            </span>
          </p>
        ) : (
          <p className="m-0 text-[13px] text-gray">
            {enabled ? copy.alertsNoThreshold : copy.alertsDisabledBody}
          </p>
        )}

        {contactMail && (
          <a
            className="text-xs font-bold text-green_dark hover:underline sm:ml-auto"
            href={`mailto:${contactMail}?subject=${encodeURIComponent(
              copy.alertsRequestSubject,
            )}`}
          >
            {copy.alertsRequestChanges}
          </a>
        )}
      </div>

      {/* Who the alerts are watched for. Only when there are any: an empty
          "sensitive groups" heading is noise in a context line. */}
      {groups.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11.5px] text-lightgray">
            {copy.notificationsRuleGroups}
          </span>
          {groups.map((group) => (
            <span
              key={group.key}
              className="inline-flex items-center gap-1 rounded-full border border-bg-gray bg-white px-2 py-0.5 text-[11.5px]"
            >
              {group.emoji && (
                <span className="font-emoji" aria-hidden="true">
                  {group.emoji}
                </span>
              )}
              {group.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Row --------------------------------------------------------------------

function NotificationRow({
  item,
  lang,
}: {
  item: InstitutionNotification;
  lang: Lang;
}) {
  const copy = useInstitutionCopy(lang);
  const isAqi = item.type === "aqi";
  const emoji = item.aqi_category ? emojiForCategory(item.aqi_category) : "";

  // The band colour from the same table the AQI card, the history chart and the
  // public map read, so a value is never a different colour here than there.
  // Guarded because a reading outside the classifiable range makes it throw
  // inside render, which unmounts the island.
  const bandColor =
    item.aqi != null && isValidAqi(item.aqi)
      ? getColorRange(item.aqi)
      : undefined;

  return (
    <li className="flex overflow-hidden rounded-lg border border-bg-gray bg-white">
      {/* A colour rail instead of a coloured row: the AQI band is the fastest
          way to read severity down a long list, but tinting whole rows would
          fight the card it sits in and make the body text harder to read.
          General notifications get the neutral surface — they have no reading
          to be a colour of. */}
      <span
        aria-hidden="true"
        className={`w-1 shrink-0 ${bandColor ? "" : "bg-bg-gray"}`}
        style={bandColor ? { backgroundColor: bandColor } : undefined}
      />

      <div className="min-w-0 flex-1 p-3.5">
        {/* Wraps rather than stacks: `items-center` would stretch the pill to
            the full row width in a column, and the timestamp and badge read as
            one line anyway. */}
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
          {isAqi && emoji && (
            <span
              className="font-emoji text-base leading-none"
              aria-hidden="true"
            >
              {emoji}
            </span>
          )}
          <p className="m-0 text-xs text-gray tabular-nums">
            {formatShortDate(item.sent_at)}
            <span className="text-lightgray">
              {" "}
              · {formatTime(item.sent_at)}
            </span>
          </p>
          {/* Neutral in both cases: the rail already carries the severity, and
              in the band's own colour. A red badge beside an orange rail says
              "danger" twice, in two different colours, for one reading. */}
          <Pill tone="neutral">
            {isAqi ? copy.notificationTypeAqi : copy.notificationTypeGeneral}
          </Pill>

          {/* The AQI reading sits with the metadata rather than in a chip of
              its own below the text: it is what distinguishes one alert from
              the next when the wording repeats, so it belongs on the line the
              eye scans. */}
          {item.aqi != null && (
            <span className="ml-auto flex items-baseline gap-1.5">
              <span className="font-serif text-lg font-bold leading-none tabular-nums">
                {formatAqi(item.aqi)}
              </span>
              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-lightgray">
                AQI
              </span>
            </span>
          )}
        </div>

        <p className="m-0 mt-2 text-[13.5px] font-bold leading-snug">
          {item.title}
        </p>
        <p className="m-0 mt-1 whitespace-pre-line text-[13.5px] leading-relaxed text-gray">
          {item.body}
        </p>

        {/* The quiet trailing line: category, threshold and sensor. Present for
            the record, deliberately not competing with the message itself. */}
        <p className="m-0 mt-2 text-[11.5px] text-lightgray">
          {[
            item.aqi_category_label,
            item.alert_threshold != null
              ? `${copy.notificationThreshold} ${item.alert_threshold}`
              : null,
            item.station_name,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>
    </li>
  );
}

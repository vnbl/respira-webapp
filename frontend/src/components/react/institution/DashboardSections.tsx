import { useState } from "react";

import type {
  InstitutionContract,
  InstitutionDashboard,
} from "../../../data/institution";
import type { Lang } from "../../../i18n/config";
import { useInstitutionCopy } from "../../../i18n/institution";
import {
  InstitutionApiError,
  fetchDashboard,
} from "../../../store/institution";
import { INSTITUTION_LOGIN_PATH } from "../../../utils/institution-session";
import { ActionLogPanel } from "./ActionLogPanel";
import { AirQualityPanel } from "./AirQualityPanel";
import { DownloadCard } from "./DownloadCard";
import { HistoryChart } from "./HistoryChart";
import { NotificationsPanel } from "./NotificationsPanel";
import { SensorStatusCard } from "./SensorStatusCard";
import { Button, Card, CardSkeleton, ErrorState, StateBlock } from "./ui";

/** How the page arrived: the server already tried to load the dashboard. */
export type InitialDashboardState =
  | { status: "ready"; dashboard: InstitutionDashboard }
  /** The institution has no contract, so no sensor — a real, expected state. */
  | { status: "no-sensor" }
  | { status: "error" };

/**
 * The dashboard's data sections.
 *
 * The payload is fetched during SSR so the page arrives complete rather than
 * flashing skeletons at a visitor whose data was already available. This island
 * takes it as a prop and only fetches on its own when the visitor retries after
 * a failure — which is why loading, error and empty states all live here even
 * though the happy path never renders the first one on load.
 */
export function DashboardSections({
  initial,
  contract,
  contactMail,
  lang,
}: {
  initial: InitialDashboardState;
  contract: InstitutionContract | null;
  contactMail: string;
  lang: Lang;
}) {
  const copy = useInstitutionCopy(lang);
  const [state, setState] = useState<
    InitialDashboardState | { status: "loading" } | { status: "expired" }
  >(initial);

  const retry = async () => {
    setState({ status: "loading" });
    try {
      setState({ status: "ready", dashboard: await fetchDashboard() });
    } catch (error) {
      if (error instanceof InstitutionApiError) {
        if (error.code === "not_found") {
          setState({ status: "no-sensor" });
          return;
        }
        if (error.code === "unauthenticated") {
          setState({ status: "expired" });
          return;
        }
      }
      setState({ status: "error" });
    }
  };

  if (state.status === "loading") {
    return (
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <CardSkeleton lines={5} />
        </div>
        <div className="lg:col-span-4">
          <CardSkeleton />
        </div>
      </div>
    );
  }

  if (state.status === "expired") {
    return (
      <Card>
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
      </Card>
    );
  }

  if (state.status === "no-sensor") {
    return (
      <Card>
        <StateBlock title={copy.noSensorTitle} body={copy.noSensorBody} />
      </Card>
    );
  }

  if (state.status === "error") {
    return (
      <Card>
        <ErrorState
          title={copy.errorTitle}
          body={copy.errorBody}
          onRetry={retry}
          retryLabel={copy.retry}
        />
      </Card>
    );
  }

  const { dashboard } = state;

  return (
    <div className="flex flex-col gap-8">
      {/* `gap-8` between sections, against the `gap-5` used *inside* a row: an
          even rhythm throughout gave the page no grouping, so a pair meant to
          be read together sat as far apart as two unrelated sections. The wider
          outer gap is what separates one subject from the next.

          Today first: what the air is doing, whether the sensor saying so is
          actually reporting, and the exports — the standing facts about the
          sensor, read together. */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <AirQualityPanel airQuality={dashboard.air_quality} lang={lang} />
        </div>
        <div className="flex flex-col gap-5 lg:col-span-4">
          <SensorStatusCard
            sensor={dashboard.sensor}
            contract={contract}
            lang={lang}
          />
          <DownloadCard lang={lang} />
        </div>
      </div>

      <HistoryChart
        history={dashboard.history}
        threshold={dashboard.alert_config.alert_threshold}
        lang={lang}
      />

      <ActionLogPanel
        stationId={dashboard.sensor.id}
        stationName={dashboard.sensor.name}
        lang={lang}
      />

      {/* What the platform sent about the sensor, as against what the action
          log holds — what the institution did about it.

          The alert configuration lives in this section's header rather than in
          a card of its own: as two sections they read as two channels, and
          "we warn you above 100 AQI" beside a separate list of warnings invites
          the question of whether those are the same warnings. The threshold is
          the rule and the list is its history, so they belong together. */}
      <NotificationsPanel
        alertConfig={dashboard.alert_config}
        contactMail={contactMail}
        lang={lang}
      />
    </div>
  );
}

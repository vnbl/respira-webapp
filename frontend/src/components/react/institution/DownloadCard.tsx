import { useEffect, useId, useState } from "react";

import type { Lang } from "../../../i18n/config";
import { useInstitutionCopy } from "../../../i18n/institution";
import {
  InstitutionApiError,
  downloadInstitutionFile,
  fetchReportMonths,
  type DownloadKind,
  type ReportMonth,
} from "../../../store/institution";
import { formatMonthName } from "../../../utils/institution-format";
import { INSTITUTION_LOGIN_PATH } from "../../../utils/institution-session";
import {
  Button,
  Card,
  CardHead,
  CardTitle,
  DownloadIcon,
  FieldLabel,
  Select,
  Skeleton,
} from "./ui";

/**
 * The two file exports.
 *
 * Each button resolves its own 404 into "not available yet" and says so under
 * itself. State is per-button rather than per-card: a failing report must not
 * disable the spreadsheet, and vice versa.
 *
 * The raw export is read live from the sensor API, so it is slower than the
 * report and can come back with gaps; both cases surface under the button that
 * caused them.
 */
export function DownloadCard({ lang }: { lang: Lang }) {
  const copy = useInstitutionCopy(lang);
  return (
    <Card>
      <CardHead>
        <CardTitle>{copy.downloadsTitle}</CardTitle>
      </CardHead>
      <MonthlyReport lang={lang} />
      {/* A rule rather than more whitespace: the report above owns a control,
          so the two downloads need a visible boundary to stop the month
          selector from reading as if it applied to both. */}
      <div className="border-t border-bg-gray pt-4">
        <DownloadButton
          kind="rawExport"
          label={copy.downloadRaw}
          note={copy.downloadRawNote}
          variant="void"
          lang={lang}
        />
      </div>
    </Card>
  );
}

/**
 * The monthly report, with the month to report on.
 *
 * Only months the sensor actually recorded are offered: the report endpoint
 * will render any month asked of it, so a free-form picker would hand back
 * empty PDFs for months the institution had no sensor. While the list loads a
 * skeleton holds the selector's exact height, so the button underneath does not
 * jump once it arrives.
 */
function MonthlyReport({ lang }: { lang: Lang }) {
  const copy = useInstitutionCopy(lang);
  const selectId = useId();
  const [months, setMonths] = useState<ReportMonth[] | undefined>();
  const [selected, setSelected] = useState<string>("");
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let active = true;
    fetchReportMonths()
      .then((data) => {
        if (!active) return;
        setMonths(data.months);
        // The backend's `default` is the month to land on: the last *complete*
        // one, since a month still in progress gives a different report on
        // every download.
        setSelected(data.default ?? data.months.at(-1)?.month ?? "");
      })
      .catch(() => {
        if (active) setLoadFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const loading = months === undefined && !loadFailed;
  const hasMonths = months !== undefined && months.length > 0;
  const noMonths = months !== undefined && months.length === 0;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <FieldLabel htmlFor={selectId}>{copy.downloadMonthly}</FieldLabel>

        {loading && (
          <>
            {/* Matches the select's height so the card does not reflow. */}
            <Skeleton className="h-[38px] w-full" />
            <span className="sr-only">{copy.reportMonthsLoading}</span>
          </>
        )}

        {hasMonths && (
          <Select id={selectId} value={selected} onChange={setSelected}>
            {[...months].reverse().map((month) => (
              <option key={month.month} value={month.month}>
                {formatMonthName(month.month, lang, month.label)}
              </option>
            ))}
          </Select>
        )}

        {noMonths && (
          // Same height as the select it stands in for, so a card with no
          // months lines up with its neighbours in the grid instead of running
          // taller. The message is short enough to fit on one line at this
          // width; `truncate` is the guard for a longer translation.
          <p
            className="flex h-[38px] items-center truncate rounded-md border border-dashed border-basedark px-3 text-[12.5px] text-gray"
            title={copy.reportNoMonths}
          >
            {copy.reportNoMonths}
          </p>
        )}

        {loadFailed && (
          <p className="text-[11.5px] text-gray">{copy.reportMonthsError}</p>
        )}
      </div>

      {/* The button keeps a fixed label. Naming the month on it was tried and
          reverted: "Descargar septiembre de 2026" wraps to two lines in this
          column, so the card changed height as the selector changed — the
          layout jumping while you pick is worse than the redundancy it saved.
          The selector directly above already states the month. */}
      <DownloadButton
        kind="monthlyReport"
        label={copy.reportDownloadPdf}
        variant="color"
        lang={lang}
        month={selected || undefined}
        disabled={loading || noMonths}
      />
    </div>
  );
}

function DownloadButton({
  kind,
  label,
  note,
  variant,
  lang,
  month,
  disabled = false,
}: {
  kind: DownloadKind;
  label: string;
  note?: string;
  variant: "color" | "void";
  lang: Lang;
  month?: string;
  disabled?: boolean;
}) {
  const copy = useInstitutionCopy(lang);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | undefined>();
  // A partial file is a warning, not a failure: it downloaded, so it reads in
  // the muted tone the notes use rather than in the error red.
  const [tone, setTone] = useState<"error" | "warning">("error");

  const handleClick = async () => {
    setBusy(true);
    setMessage(undefined);
    try {
      const { missingRanges } = await downloadInstitutionFile(kind, { month });
      if (missingRanges > 0) {
        setTone("warning");
        setMessage(copy.downloadPartial);
      }
    } catch (error) {
      setTone("error");
      if (error instanceof InstitutionApiError) {
        if (error.code === "unauthenticated") {
          window.location.assign(INSTITUTION_LOGIN_PATH);
          return;
        }
        setMessage(
          error.code === "unavailable"
            ? copy.downloadUnavailable
            : copy.downloadError,
        );
      } else {
        setMessage(copy.downloadError);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      <Button
        variant={variant}
        block
        onClick={handleClick}
        disabled={busy || disabled}
      >
        <DownloadIcon />
        {busy ? copy.downloadPreparing : label}
      </Button>
      {note && <span className="text-[11.5px] text-lightgray">{note}</span>}
      {message && (
        <span
          role="alert"
          className={
            tone === "warning"
              ? "text-[11.5px] text-gray"
              : "text-[11.5px] text-aqi-red-dark"
          }
        >
          {message}
        </span>
      )}
    </div>
  );
}

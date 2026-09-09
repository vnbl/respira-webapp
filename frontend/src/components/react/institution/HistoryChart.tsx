import { useMemo, useState, type PointerEvent } from "react";

import { AQI_COLORS, AQI_RANGES } from "../../../data/constants";
import type { DashboardHistoryPoint } from "../../../data/institution";
import type { Lang } from "../../../i18n/config";
import { format, useInstitutionCopy } from "../../../i18n/institution";
import {
  formatAqi,
  formatDate,
  formatMonth,
  parseApiDate,
} from "../../../utils/institution-format";
import { getColorRange } from "../../../utils";
import { Card, CardHead, CardTitle, Pill, StateBlock } from "./ui";

// The SVG is drawn in a fixed coordinate system and scaled uniformly by CSS, so
// there is no layout measurement to do and nothing that can differ between the
// server render and the browser's.
const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 220;
const PAD_TOP = 8;
const PAD_BOTTOM = 24;
const PLOT_HEIGHT = VIEW_HEIGHT - PAD_TOP - PAD_BOTTOM;

/** Headroom so the top of the series is never flush against the frame. */
const Y_STEP = 50;
const MIN_Y_MAX = 150;

type Point = {
  date: Date;
  aqi: number;
};

type Scales = {
  x: (date: Date) => number;
  y: (aqi: number) => number;
  yMax: number;
};

const buildScales = (points: Point[], threshold: number | null): Scales => {
  const first = points[0].date.getTime();
  const last = points[points.length - 1].date.getTime();
  const span = last - first || 1;

  const highest = Math.max(
    ...points.map((point) => point.aqi),
    threshold ?? 0,
    MIN_Y_MAX,
  );
  const yMax = Math.ceil(highest / Y_STEP) * Y_STEP;

  return {
    x: (date) => ((date.getTime() - first) / span) * VIEW_WIDTH,
    y: (aqi) =>
      PAD_TOP + PLOT_HEIGHT - (Math.min(aqi, yMax) / yMax) * PLOT_HEIGHT,
    yMax,
  };
};

/** First-of-month positions, for the only x ticks the series needs. */
const monthTicks = (points: Point[]): Point[] => {
  const seen = new Set<string>();
  const ticks: Point[] = [];
  for (const point of points) {
    const key = `${point.date.getFullYear()}-${point.date.getMonth()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    // Skip a tick sitting on the left edge, where its label would be clipped.
    if (point !== points[0]) ticks.push(point);
  }
  return ticks;
};

export function HistoryChart({
  history,
  threshold,
  lang,
}: {
  history: DashboardHistoryPoint[];
  threshold: number | null;
  lang: Lang;
}) {
  const copy = useInstitutionCopy(lang);
  const [hovered, setHovered] = useState<Point | undefined>();

  const points = useMemo<Point[]>(
    () =>
      history
        // Days with no reading arrive as gaps, but guard the shape anyway:
        // `getColorRange` throws on a negative or non-finite AQI, and a throw
        // inside render unmounts the whole island.
        .filter(
          (point): point is { date: string; aqi: number } =>
            typeof point.aqi === "number" &&
            Number.isFinite(point.aqi) &&
            point.aqi >= 0,
        )
        .map((point) => ({ date: parseApiDate(point.date), aqi: point.aqi }))
        .sort((a, b) => a.date.getTime() - b.date.getTime()),
    [history],
  );

  const scales = useMemo(
    () => (points.length >= 2 ? buildScales(points, threshold) : undefined),
    [points, threshold],
  );

  if (!scales) {
    return (
      <Card tone="main">
        <CardHead>
          <CardTitle level="main">{copy.historyTitle}</CardTitle>
        </CardHead>
        <StateBlock
          title={copy.historyEmptyTitle}
          body={copy.historyEmptyBody}
        />
      </Card>
    );
  }

  const { x, y, yMax } = scales;
  const last = points[points.length - 1];
  const line = points.map((point) => `${x(point.date)},${y(point.aqi)}`);
  const baseline = y(0);
  const showThreshold = threshold != null && threshold > 0 && threshold <= yMax;

  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width) return;
    const ratio = (event.clientX - rect.left) / rect.width;
    const index = Math.round(ratio * (points.length - 1));
    setHovered(points[Math.max(0, Math.min(points.length - 1, index))]);
  };

  return (
    <Card tone="main">
      <CardHead>
        <CardTitle level="main">{copy.historyTitle}</CardTitle>
        <span className="ml-auto">
          <Pill>{copy.historySubtitle}</Pill>
        </span>
      </CardHead>

      <div className="relative">
        <svg
          viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
          className="block h-auto w-full touch-none"
          role="img"
          aria-label={`${copy.historyTitle}. ${format(copy.historyChartLabel, {
            days: points.length,
            min: formatAqi(Math.min(...points.map((point) => point.aqi))),
            max: formatAqi(Math.max(...points.map((point) => point.aqi))),
          })}`}
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHovered(undefined)}
        >
          {/* AQI bands, kept faint: context behind the series, not a subject. */}
          {AQI_RANGES.map(([, bandTop], index) => {
            const bottom = index === 0 ? 0 : AQI_RANGES[index - 1][1];
            if (bottom >= yMax) return null;
            const top = Math.min(bandTop, yMax);
            return (
              <rect
                key={bandTop}
                x={0}
                y={y(top)}
                width={VIEW_WIDTH}
                height={Math.max(0, y(bottom) - y(top))}
                fill={AQI_COLORS[index]}
                opacity={0.22}
              />
            );
          })}

          {monthTicks(points).map((tick) => (
            <g key={tick.date.toISOString()}>
              <line
                x1={x(tick.date)}
                x2={x(tick.date)}
                y1={PAD_TOP}
                y2={PAD_TOP + PLOT_HEIGHT}
                stroke="#1a1a1a"
                strokeOpacity={0.12}
                strokeWidth={1}
              />
              <text
                x={x(tick.date) + 6}
                y={VIEW_HEIGHT - 8}
                fill="#535353"
                fontSize={11}
              >
                {formatMonth(tick.date)}
              </text>
            </g>
          ))}

          <polygon
            points={`0,${baseline} ${line.join(" ")} ${VIEW_WIDTH},${baseline}`}
            fill="#4B7A3D"
            opacity={0.12}
          />
          <polyline
            points={line.join(" ")}
            fill="none"
            stroke="#4B7A3D"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {showThreshold && (
            <line
              x1={0}
              x2={VIEW_WIDTH}
              y1={y(threshold)}
              y2={y(threshold)}
              stroke="#8E2A2A"
              strokeWidth={1.5}
              strokeDasharray="6 5"
            />
          )}

          {/* The most recent day, emphasised: it is the point people look for. */}
          <circle
            cx={x(last.date)}
            cy={y(last.aqi)}
            r={4.5}
            fill={getColorRange(last.aqi)}
            stroke="#1a1a1a"
            strokeWidth={1.5}
          />

          {hovered && (
            <>
              <line
                x1={x(hovered.date)}
                x2={x(hovered.date)}
                y1={PAD_TOP}
                y2={PAD_TOP + PLOT_HEIGHT}
                stroke="#1a1a1a"
                strokeOpacity={0.35}
                strokeWidth={1}
              />
              <circle
                cx={x(hovered.date)}
                cy={y(hovered.aqi)}
                r={5}
                fill="#4B7A3D"
                stroke="#FFFFFF"
                strokeWidth={2}
              />
            </>
          )}
        </svg>

        {hovered && (
          <div
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-md bg-near_black px-2.5 py-1.5 text-xs text-white tabular-nums"
            style={{
              left: `${(x(hovered.date) / VIEW_WIDTH) * 100}%`,
              top: `${(y(hovered.aqi) / VIEW_HEIGHT) * 100}%`,
            }}
          >
            <b className="block font-bold">{formatAqi(hovered.aqi)} AQI</b>
            <span className="text-lightgray">
              {formatDate(hovered.date.toISOString())}
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[11.5px] text-gray">
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="block h-0.5 w-3 rounded-sm bg-green_dark"
          />
          {copy.historyLegendSeries}
        </span>
        {showThreshold && (
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="block h-0 w-3 border-t-2 border-dashed border-aqi-red-dark"
            />
            {copy.historyLegendThreshold} ({threshold})
          </span>
        )}
      </div>
    </Card>
  );
}

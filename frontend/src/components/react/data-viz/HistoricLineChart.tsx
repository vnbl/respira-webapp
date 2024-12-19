import React, { useMemo, useState } from "react";
import { ResponsiveLine, type CustomLayerProps } from "@nivo/line";
import { useStore } from "@nanostores/react";
import {
  errorHistoricForecast,
  historicForecastData,
  loadingHistoricForecast,
} from "../../../store/statistics";
import { useAnimatedPath } from "@nivo/core";
import { type LegendProps } from "@nivo/legends";

import { animated } from "@react-spring/web";
type SymbolProps = Exclude<
  LegendProps["symbolShape"],
  "circle" | "diamond" | "square" | "triangle" | undefined
> extends React.FC<infer P>
  ? P & { opacity?: number }
  : never;

const SymbolLine = ({ x, y, size, fill, id }: SymbolProps) => {
  return (
    <g transform={`translate(${x},${y})`}>
      <line
        x1={-size}
        y1="5"
        x2={size}
        y2="5"
        strokeDasharray={id === "Medición real" ? "" :"4"}
        style={{
          stroke: fill,
          strokeWidth: 4,
          pointerEvents: "none",
        }}
      />
    </g>
  );
};

type LinesItemProps = Pick<CustomLayerProps, "lineGenerator"> & {
  color: string;
  points: Record<"x" | "y", number>[];
  thickness: number;
  dashed: boolean;
};

const props = {
  lineWidth: 4,
  enableSlices: "x",
  margin: { top: 20, right: 20, bottom: 60, left: 80 },
} as const;

function LinesItem({
  lineGenerator,
  points,
  color: stroke,
  thickness: strokeWidth,
  dashed,
}: LinesItemProps) {
  const [styles, setStyles] = useState({
    stroke,
    strokeWidth,
    strokeDasharray: dashed ? "3,6" : "",
  });

  const path = useMemo(() => lineGenerator(points), [lineGenerator, points]);
  if (!path) return [];
  const animatedPath = useAnimatedPath(path);

  return (
    <animated.path
      d={animatedPath}
      fill="none"
      onMouseEnter={() =>
        setStyles({
          strokeWidth: strokeWidth,
          stroke: strokeWidth.toString(),
          strokeDasharray: "",
        })
      }
      onMouseLeave={() =>
        setStyles({ stroke, strokeWidth, strokeDasharray: "" })
      }
      {...styles}
    />
  );
}

function Lines({ lineGenerator, lineWidth, series }: CustomLayerProps) {
  return series
    .slice(0)
    .map(({ id, data, color }, index) => (
      <LinesItem
        key={id}
        points={data.map((d) => d.position)}
        lineGenerator={lineGenerator}
        color={color ?? "black"}
        thickness={lineWidth ?? 5}
        dashed={index > 0}
      />
    ));
}

export const HistoricLineChart = () => {
  const data = useStore(historicForecastData);
  const error = useStore(errorHistoricForecast);
  const loading = useStore(loadingHistoricForecast);
  const formattedData = React.useMemo(() => {
    if (!data) {
      return undefined;
    }
    const filler = data.aqi_level[data.aqi_level.length - 1];
    return [
      {
        color: "hsla(43, 84%, 49%)",
        id: "Medición real",
        data: data.aqi_level.map((d) => ({
          x: d.timestamp,
          y: d.value,
          color: "hsla(43, 84%, 49%, 1)",
        })),
      },
      {
        color: "hsla(126, 72%, 45%)",
        id: "Predicción 6 horas",
        data: [{ x: filler.timestamp, y: filler.value }].concat(
          data.forecast_6h.map((d) => ({ x: d.timestamp, y: d.value }))
        ),
      },
      {
        color: "hsla(194, 62%, 53%)",
        id: "Predicción 12 horas",
        data: [{ x: filler.timestamp, y: filler.value }].concat(
          data.forecast_12h.map((d) => ({ x: d.timestamp, y: d.value }))
        ),
      },
    ];
  }, [data]);

  return (
    <>
      {loading && (
        <svg
          className="animate-spin h-5 w-5 mr-3 ..."
          viewBox="0 0 24 24"
        ></svg>
      )}
      {formattedData && (
        <ResponsiveLine
          colors={["#E5AA14", "#21C731", "#3BADD1"]}
          data={formattedData}
          animate
          margin={{ top: 150, right: 110, bottom: 50, left: 60 }}
          enablePoints={false}
          yScale={{
            type: "linear",
            min: 0,
            max: "auto",
            stacked: false,
            reverse: false,
          }}
          enableGridX={false}
          enableSlices="x"
          axisBottom={{
            format: "%H %M",
            legendOffset: -12,
            tickValues: "every 2 hour",
          }}
          curve="linear"
          xFormat="time:%Y-%m-%d"
          xScale={{
            format: "%Y-%m-%dT%H:%M:%S",
            precision: "hour",
            type: "time",
            useUTC: false,
            min: "auto",
            max: "auto",
          }}
          axisTop={null}
          axisRight={null}
          axisLeft={{
            tickSize: 0,
            tickPadding: 5,
            tickRotation: 0,
            legend: "AQI",
            legendOffset: -40,
            legendPosition: "middle",
            truncateTickAt: 0,
          }}
          pointSize={10}
          pointColor={{ theme: "background" }}
          pointBorderWidth={2}
          pointBorderColor={{ from: "serieColor" }}
          pointLabel="data.yFormatted"
          pointLabelYOffset={-12}
          enableTouchCrosshair={true}
          useMesh={true}
          layers={[
            // includes all default layers
            "grid",
            "markers",
            "axes",
            "areas",
            "crosshair",
            "slices",
            Lines,
            "mesh",
            "legends",
          ]}
          legends={[
            {
              anchor: "top-right",
              direction: "column",
              justify: false,
              translateX: 0,
              translateY: -100,
              itemsSpacing: 0,
              itemDirection: "left-to-right",
              itemWidth: 80,
              itemHeight: 20,
              itemOpacity: 0.75,
              symbolSize: 12,
              symbolShape: SymbolLine,
              symbolBorderColor: "rgba(0, 0, 0, .5)",
              effects: [
                {
                  on: "hover",
                  style: {
                    itemBackground: "rgba(0, 0, 0, .03)",
                    itemOpacity: 1,
                  },
                },
              ],
            },
          ]}
        />
      )}
    </>
  );
};

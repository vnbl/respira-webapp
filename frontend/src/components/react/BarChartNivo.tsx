import React from "react";

import { AQI_COLORS, AQI_RANGES } from "../../data/constants";
import { getAQIIndex } from "../../utils";
import { ResponsiveBar } from "@nivo/bar";
import moment from "moment";

const getColorRange = (aqi) => AQI_COLORS[getAQIIndex(aqi)];

const customTooltip = ({ id, value, color }) => (
  <div className="bg-black p-2 rounded flex flex-col text-white font-serif">
    <p className="text-xs">Min: {value}</p>
  </div>
);

export const BarChart = ({ data }: any) => {
  console.log(data)
  const maxValue = React.useMemo((d)=> {
    return Math.max(...data.map(d=>d.value))
  }, [data])
  console.log(maxValue)
  return (
    <ResponsiveBar
      data={data}
      valueScale={{ type: "symlog" }}
      padding={0.1}
      motionConfig="wobbly"
      keys={["value"]}
      indexBy="timestamp"
      enableGridY={false}
      colors={(datum) => getColorRange(datum.value)}
      enableLabel={false}
      axisLeft={null}
      minValue={0}
      maxValue={600}
      enableTotals={true}
      totalsOffset={10}
      tooltip={(d) => customTooltip(d)}
      axisBottom={{
        tickSize: 60,
        tickPadding: 5,
        tickRotation: 0,
      }}
      theme={{
        text: {
          fontSize: 12,
          fill: "#A1A1A1",
        },
        axis: {
          domain: {
            line: {
              stroke: "#ECECEC",
              strokeWidth: 2,
            },
          },
        },
      }}
    />
  );
};

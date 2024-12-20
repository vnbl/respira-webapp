import React from "react";
import { getColorRange } from "../../utils";
import { ResponsiveBar} from "@nivo/bar";
import { timeFormat } from "d3-time-format";
import { scaleTime } from "d3-scale";
import {DateTime} from "luxon"

const customTooltip = ({ value }: { value: number }) => (
  <div className="flex flex-col rounded bg-black p-2 font-serif text-white">
    <p className="text-xs">{Math.round(value)}</p>
  </div>
);

export const BarChart = ({ data }: any) => {
  const maxValue = React.useMemo(
    () => {
      return Math.max(...data.map((d:any) => d.value));
    },
    [data]
  );

  const formatter = timeFormat("%-I:%M %p");
  const formatDateToTimezone = (date:Date) => {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    const tzOffset = DateTime.fromJSDate(date).setZone(tz).offset; // minutes
    return new Date(date.getTime() + (tzOffset - 60) * 60000);
  }
  const timeScaleTicks: string[] = React.useMemo(() => {
    const scale = scaleTime().domain([
      new Date(data[0].timestamp),
      new Date(data[data.length - 1].timestamp),
    ])
    const ticks = scale.ticks(data.length > 6 ? 6 : 10)
    return ticks.map((tick) => formatter(formatDateToTimezone(tick)))
  }, data)

  return (
    <ResponsiveBar
      data={data}
      motionConfig="wobbly"
      keys={["value"]}
      indexBy="timestamp"
      padding={0.05}
      enableGridY={false}
      colors={(datum) => getColorRange(datum.value || 0)}
      enableLabel={false}
      margin={{ top: maxValue > 300 ? 30 : 15, right: 0, bottom: 25, left: 0 }}
      axisLeft={null}
      minValue={0}
      maxValue={maxValue}
      enableTotals={true}
      totalsOffset={10}
      tooltip={(d) => customTooltip(d)}
      valueScale={{
        type: "symlog",
        min: 0 ,
        max: 400,
      }}
      valueFormat={(value) => Math.round(value).toString()}
      axisBottom={{
        tickSize: 5,
        tickPadding: 5,
        tickRotation: 0,
        format: (val) => { 
          const formatted = formatter(formatDateToTimezone(new Date(val)));
          return timeScaleTicks.includes(formatted) ? formatted: '' 
        },
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

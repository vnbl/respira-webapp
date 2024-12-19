// install (please try to align the version of installed @nivo packages)
// yarn add @nivo/boxplot
import { useStore } from "@nanostores/react";
import { ResponsiveBoxPlot } from "@nivo/boxplot";
import { DateTime } from "luxon";
import { boxplotMonthData, boxplotWeekData, boxplotYearData } from "../../../store/statistics";
const data = {
  x: [
    "2024-12-18",
    "2024-12-17",
    "2024-12-16",
    "2024-12-15",
    "2024-12-14",
    "2024-12-13",
    "2024-12-12",
  ],
  q1: [57.5, 29, 16.25, 10, 7.25, 7, 29],
  median: [60, 31, 19, 10, 8, 9, 30],
  q3: [64, 44, 21, 13, 9, 10.25, 30.75],
  lowerfence: [57, 29, 14, 10, 7, 7, 26.375],
  upperfence: [65, 56, 27, 14, 10, 15.125, 31],
};
const quantiles = [0, 0.25, 0.5, 0.75, 1];

const formatterWeek =(date: string, {index}: {index?:number}) => DateTime.fromFormat(date, "yyyy-mm-dd", { locale: "es" })
.weekdayShort
const formatterMonth =(date: string, {index}: {index?:number}) =>  index !== undefined ? (index+1) + "W": undefined
const formatterYear =(date: string, {index}: {index?:number}) => date

const processData = (data, formatter) => {
  if(!data){return}
  const size = data["x"].length;
  return data["x"].reverse().map((value, index) => ({
    group: formatter(data["x"][index], {index}),
    subGroup: "",
    mean: data["median"][index],
    quantiles: quantiles,
    values: [
      data["lowerfence"][index],
      data["q1"][index],
      data["median"][index],
      data["q3"][index],
      data["upperfence"][index],
    ],
    n: size,
    extrema: [data["lowerfence"][index], data["upperfence"][index]],
  }));
};


export const BoxPlotChart = ({ period }: { period: "7d" | "30d" | "1y" }) => {
  let data;
  if (period === "7d") {
    data = processData(useStore(boxplotWeekData), formatterWeek);
  }
  if (period === "30d") {
    data = processData(useStore(boxplotMonthData), formatterMonth);
  }
  if (period === "1y") {
    data = processData(useStore(boxplotYearData), formatterYear);
  }

  return (
    <>
      {data ? (
        <ResponsiveBoxPlot
          data={data}
          colors={["#EEC3A4"]}
          medianColor={"#8F4712"}
          whiskerColor={"#818181"}
          margin={{ top: 60, right: 30, bottom: 60, left: 30 }}
          subGroups={[]}
          padding={0.6}
          theme= {{
            translation: {
              n: 'n',
              Summary: 'Resumen',
              mean: 'Media',
              min: 'min',
              max: 'max',
              Quantiles: 'Cuantiles'
            },
          }}
        />
      ) : (
        <svg className="animate-spin h-5 w-5 mr-3 ..." viewBox="0 0 24 24" />
      )}
    </>
  );
};

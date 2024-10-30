import * as React from "react";

import { useStore } from "@nanostores/react";
import { region } from "../../store/map";
import { BarChart as Chart } from "./BarChartNivo";
import { isBackendAvailable } from "../../store/store";

export const Card = (props) => {
  const backendAvailable = useStore(isBackendAvailable);
  const data = useStore(region);
  console.log(data);
  return (
    <div className="bg-white min-h-[calc(100%-6rem)] md:w-1/3 md:absolute md:top-0 rounded-xl z-20 md:ml-8 md:mt-8 drop-shadow-lg flex flex-col p-8 space-y-4">
      {!backendAvailable && (
        <div className="w-full h-full content-center justify-center">
          <p className="font-bold text-lg text-center">
            ⚠️ Error conectándose al backend
          </p>
        </div>
      )}
      {backendAvailable && data && (
        <>
          {props.header}
          {props.header_forecast_six}
          <div className="h-[100px] w-full">
            <Chart data={data.forecast_6h} client:only />
          </div>
          {props.header_forecast_twelve}
          <div className="h-[100px] w-full pb-2">
            <Chart data={data.forecast_12h} client:only />
          </div>
          {props.action}
        </>
      )}
    </div>
  );
};

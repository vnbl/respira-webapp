import * as React from "react";

import { useStore } from "@nanostores/react";
import { region } from "../../store/map";
import { BarChart as Chart } from "./BarChartNivo";
import { Slider } from "./Slider";
import {AQICard} from "./AQICardReactive"
import { isBackendAvailable } from "../../store/store";
import { selectedStation } from "../../store/map";
import {AQI} from "../../data/cards";
import { getAQIIndex } from '../../utils';

export const Card = (props) => {
  const backendAvailable = useStore(isBackendAvailable);
  const station = useStore(selectedStation);
  const data = useStore(region);
  console.log(data, station)

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
          <div className="mt-6">
            <Slider value={station ? station.aqi_level : data.aqi} />
            <div className="mt-6">
              <AQICard card={AQI[getAQIIndex(station? station.aqi_level : data?.aqi || 0)]} />
            </div>
          </div>
          {props.header_forecast_six}
          <div className="h-[100px] w-full">
            <Chart
              data={station ? station.forecast_6h : data.forecast_6h}
              client:only
            />
          </div>
          {props.header_forecast_twelve}
          <div className="h-[100px] w-full pb-2">
            <Chart
              data={station ? station.forecast_12h : data.forecast_12h}
              client:only
            />
          </div>
          {props.action}
        </>
      )}
    </div>
  );
};

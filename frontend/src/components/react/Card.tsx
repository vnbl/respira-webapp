import * as React from 'react'

import { useStore } from '@nanostores/react'
import { region } from '../../store/map'
import { BarChart as Chart } from './BarChartNivo'
import { Slider } from './Slider'
import { AQICard } from './AQICardReactive'
import { isBackendAvailable } from '../../store/store'
import { selectedStation } from '../../store/map'
import { AQI } from '../../data/cards'
import { getAQIIndex } from '../../utils'

export const Card = (props: any) => {
  const backendAvailable = useStore(isBackendAvailable)
  const station = useStore(selectedStation)
  const data = useStore(region)

  return (
    <div
      className={`pointer-events-auto z-20 flex w-full flex-col space-y-6 rounded-xl bg-white p-8 drop-shadow-lg md:ml-8 md:mt-8 md:min-h-full md:w-2/3`}
    >
      {!backendAvailable && (
        <div className="h-full w-full content-center justify-center">
          <p className="text-center text-lg font-bold">
            ⚠️ Error conectándose al backend
          </p>
        </div>
      )}
      {backendAvailable && data && (
        <>
          {props.header}
          <h6 className="w-auto text-center font-serif text-lg font-bold">
            {!station ? 'Media General' : station.name}
          </h6>
          <div>
            <Slider value={station ? station.aqi : data.aqi} />
            <div className="mt-6">
              <AQICard
                card={AQI[getAQIIndex(station ? station.aqi : data?.aqi || 0)]}
              />
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
  )
}

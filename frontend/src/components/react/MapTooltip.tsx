import * as React from 'react'
import { getAQIIndex } from '../../utils'
import { AQI } from '../../data/cards'
import { useStore } from '@nanostores/react'
import { region } from '../../store/map'

export const MapTooltip = () => {
  const data = useStore(region)
  const card = React.useMemo(() => {
    if (!data) {
      return undefined
    }
    return AQI[getAQIIndex(data.aqi)]
  }, [data])
  return (
    <>
      {card ? (
        <div className="absolute bottom-5 left-5 flex h-fit w-fit space-x-2 rounded-lg bg-[#535353] p-2 md:left-auto md:right-10 md:top-10 md:flex-col md:space-x-0 md:p-3">
          <div className="flex flex-row items-center space-x-2">
            <p className="text-sm text-white">Media: {card.title}</p>
            <div className={`bg-${card.color} h-4 w-4`} />
          </div>
          {data.aqi >= 50 && (
            <a>
              <p className="text-sm text-white underline">Recomendaciones</p>
            </a>
          )}
        </div>
      ) : undefined}
    </>
  )
}

import * as React from 'react'
import SliderPin from '../react/SliderPin'
import { getAQIIndex, getColorRange } from '../../utils'

const calculateOffset = (value: number) => {
  const index = getAQIIndex(value)
  return index * (100 / 6) + 8
}

export const Slider = ({ value }: { value: number }) => {
  return (
    <>
      <div className={'fixed -mt-5 flex w-[86%] flex-row'}>
        <div
          style={{
            width: `calc(${calculateOffset(value)}% - 15px)`,
          }}
        />
        <SliderPin value={value} fill={getColorRange(value)} />
      </div>
      <div className="flex flex-row">
        <div className="w-1/2 text-xs"></div>
        <p className="w-full text-center text-xs font-bold text-lightgray">
          50
        </p>
        <p className="w-full text-center text-xs font-bold text-lightgray">
          100
        </p>
        <p className="w-full text-center text-xs font-bold text-lightgray">
          1 50
        </p>
        <p className="w-full text-center text-xs font-bold text-lightgray">
          200
        </p>
        <p className="w-full text-center text-xs font-bold text-lightgray">
          300
        </p>
        <div className="w-1/2 text-xs"></div>
      </div>

      <div className="flex flex-row divide-x-2">
        <div className="h-6 w-full rounded-l-full border-y-2 border-l-2 border-gray bg-aqi-green-dark"></div>
        <div className="h-6 w-full border-2 border-gray bg-aqi-yellow-dark"></div>
        <div className="h-6 w-full border-2 border-gray bg-aqi-orange-dark"></div>
        <div className="h-6 w-full border-2 border-gray bg-aqi-red-dark"></div>
        <div className="h-6 w-full border-2 border-gray bg-aqi-purple-dark"></div>
        <div className="h-6 w-full rounded-r-full border-2 border-gray bg-aqi-vermellion-dark"></div>
      </div>
    </>
  )
}

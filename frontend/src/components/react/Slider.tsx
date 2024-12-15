import * as React from "react";
import SliderPin from "../react/SliderPin";
import { getAQIIndex, getColorRange } from "../../utils";


const calculateOffset = (value:number) => {
  const index = getAQIIndex(value);
  return index * (100 / 6) + 10;
};

export const Slider = ({ value }: {value: number}) => {
  return (
    <>
      <div className={"flex flex-row fixed w-[86%] -mt-2"}>
        <div
          style={{
            width: `calc(${calculateOffset(value)}% - 25px)`,
          }}
        />
        <SliderPin value={value} fill={getColorRange(value)} />
      </div>
      <div className="flex flex-row mt-4">
        <div className="text-xs w-1/2"></div>
        <p className="text-sm font-bold w-full text-lightgray text-center">
          50
        </p>
        <p className="text-sm font-bold w-full text-lightgray text-center">
          100
        </p>
        <p className="text-sm font-bold w-full text-lightgray text-center">
          1 50
        </p>
        <p className="text-sm font-bold w-full text-lightgray text-center">
          200
        </p>
        <p className="text-sm font-bold w-full text-lightgray text-center">
          300
        </p>
        <div className="text-sm w-1/2"></div>
      </div>

      <div className="flex flex-row divide-x-2">
        <div className="bg-aqi-green-dark h-[2rem] w-full rounded-l-full border-y-3 border-l-3 border-gray"></div>
        <div className="bg-aqi-yellow-dark h-[2rem] w-full border-3 border-gray"></div>
        <div className="bg-aqi-orange-dark h-[2rem] w-full border-3 border-gray"></div>
        <div className="bg-aqi-red-dark h-[2rem] w-full border-3 border-gray"></div>
        <div className="bg-aqi-purple-dark h-[2rem] w-full border-3 border-gray"></div>
        <div className="bg-aqi-vermellion-dark h-[2rem] w-full rounded-r-full border-3 border-gray"></div>
      </div>
    </>
  );
};

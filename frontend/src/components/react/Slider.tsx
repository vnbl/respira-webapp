import * as React from "react";
import SliderPin from "../react/SliderPin";
import { getAQIIndex, getColorRange } from "../../utils";


const calculateOffset = (value) => {
  const index = getAQIIndex(value);
  return index * (100 / 6) + 8;
};

export const Slider = ({ value }) => {
  return (
    <>
      <div className={"flex flex-row fixed w-[86%] -mt-6"}>
        <div
          style={{
            width: `calc(${calculateOffset(value)}% - 15px)`,
          }}
        />
        <SliderPin value={value} fill={getColorRange(value)} />
      </div>
      <div className="flex flex-row">
        <div className="text-xs w-1/2"></div>
        <p className="text-xs font-bold w-full text-lightgray text-center">
          50
        </p>
        <p className="text-xs font-bold w-full text-lightgray text-center">
          100
        </p>
        <p className="text-xs font-bold w-full text-lightgray text-center">
          1 50
        </p>
        <p className="text-xs font-bold w-full text-lightgray text-center">
          200
        </p>
        <p className="text-xs font-bold w-full text-lightgray text-center">
          300
        </p>
        <div className="text-xs w-1/2"></div>
      </div>

      <div className="flex flex-row divide-x-2">
        <div className="bg-aqi-green-dark h-6 w-full rounded-l-full border-y-2 border-l-2 border-gray"></div>
        <div className="bg-aqi-yellow-dark h-6 w-full border-2 border-gray"></div>
        <div className="bg-aqi-orange-dark h-6 w-full border-2 border-gray"></div>
        <div className="bg-aqi-red-dark h-6 w-full border-2 border-gray"></div>
        <div className="bg-aqi-purple-dark h-6 w-full border-2 border-gray"></div>
        <div className="bg-aqi-vermellion-dark h-6 w-full rounded-r-full border-2 border-gray"></div>
      </div>
    </>
  );
};

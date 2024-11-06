import * as React from "react";
import { getAQIIndex } from "../../utils";
import { AQI } from "../../data/cards";
import { useStore } from "@nanostores/react";
import { region } from "../../store/map";

export const MapTooltip = () => {
  const data = useStore(region);
  const card = React.useMemo(()=> {
    if(!data){
      return undefined
    }
    return AQI[getAQIIndex(data.aqi)]
  }, [data])
  return (
    <>
      {card ? (
        <div className="bg-[#535353] absolute bottom-5 left-5 md:top-10 md:right-10 md:left-auto  w-fit h-fit rounded-lg  p-2 md:p-3 flex md:flex-col md:space-x-0 space-x-2">
          <div className="flex flex-row space-x-2 items-center">
          <p className="text-white text-sm">
            Media: {card.title}
          </p>
          <div className={`bg-${card.color} h-4 w-4`} />
          </div>
          {data.aqi >=50 && <a><p className="text-white underline text-sm">Recomendaciones</p></a>}
        </div>
      ) : undefined}
    </>
  );
};

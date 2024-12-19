import React from "react";
import { useStore } from "@nanostores/react";

import {
  statisticsSelectedStation,
} from "../../../store/statistics";

const HeaderStatistics = (props: any) => {
  const station = useStore(statisticsSelectedStation);
  return (
    <>
    <h2 className="font-serif font-bold text-[2.1rem] text-black"
      >Estación {station?.id}</h2>
    <h3 className="font-normal font-sans  text-[1.875rem] text-black">Estación {station?.name}</h3>
    </>
  );
};

export { HeaderStatistics };

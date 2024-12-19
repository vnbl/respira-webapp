import React from "react";
import { useStore } from "@nanostores/react";

import { loadingStations, stations } from "../../../store/map";
import type { DynamicMenuItem } from "../../../data/menu";

const DropdownData = ({ baseRoute, titleKey, subtitleKey }: DynamicMenuItem) => {
  const data = useStore(stations);
  const loading = useStore(loadingStations);

  return (
    <>
      {loading && (
        <div className
          ="animate-pulse flex flex-col space-y-4">
          <div className
            ="h-10 w-full bg-basedark rounded"></div>
          <div className
            ="h-10 w-full bg-basedark rounded"></div>
          <div className
            ="h-10 w-full bg-basedark rounded"></div>
        </div>
      )}
      {!loading &&
        data &&
        data.map((val: any) => (
          <a href={baseRoute + "/" + val["id"]} key={val["id"]}>
            <li>
              <p className="font-serif font-bold text-[1rem] text-black">
                Estación {val[titleKey]}
              </p>
              <p className="font-sans text-[0.75rem] text-black">{val[subtitleKey]}</p>
            </li>
          </a>
        ))}
    </>
  );
};

export { DropdownData };

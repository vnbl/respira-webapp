import * as React from "react";
import { getTextColor } from '../../utils';

export const AQICard = ({ card }) => {
  return (
    <div className={`bg-${card.color} w-full  rounded-xl p-10`}>
      <div className="flex flex-row w-full min-h-20">
        <div className="flex flex-col align-center justify-center flex-1 mr-4">
          <p className="text-5xl text-center font-emoji">{card.icon}</p>
        </div>
        <div className="flex flex-col w-full justify-center">
          <div className="flex flex-row mb-2 flex-wrap">
            <h5
              className={`font-serif font-bold text-[1.25rem] text-${
                getTextColor(card.color) || "black"
              }  grow`}
            >
              {card.title}
            </h5>
            <h5
              className={`font-serif font-bold text-[1.25rem] text-${
                getTextColor(card.color) || "black"
              }`}
            >
              {card.range[0]}-{card.range[1]}
            </h5>
          </div>
          <p
            className={`font-sans text-[1rem] text-${
              getTextColor(card.color) || "black"
            } `}
          >
            {card.description}
          </p>
        </div>
      </div>
    </div>
  );
};

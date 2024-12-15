import * as React from "react";
import { getTextColor } from '../../utils';
import type { AQICard as CardType } from "../../data/cards";

export const AQICard = ({ card, variant = 'normal' }: { card: CardType, variant?: 'normal' | 'recommendations' }) => {
  return (

    <div className={`bg-${card.color} w-full  rounded-xl p-10`}>
      <div className="flex flex-row w-full min-h-20">
        <div className="flex flex-col align-center justify-center mr-4">
          <img alt={card.icon.alt} src={card.icon.path.src} height={60} width={60} />
        </div>
        <div className="flex flex-col w-full justify-center">
          <div className="flex flex-row mb-2 flex-wrap">
            <h5
              className={`font-sans font-bold text-[1.25rem] text-${getTextColor(card.color) || "black"
                }  grow`}
            >
              {card.title}
            </h5>
            <h5
              className={`font-sans font-bold text-[1.25rem] text-${getTextColor(card.color) || "black"
                }`}
            >
              {card.range[0]}-{card.range[1]}
            </h5>
          </div>
          {variant === 'normal' ? (<p
            className={`font-sans text-[1rem] text-${getTextColor(card.color) || "black"
              } `}
          >
            {card.description}
          </p>) : <ul className={`list-disc pl-4 text-${getTextColor(card.color) || "black"} font-normal font-sans`}>
            {card.recommendations.map((item, key) => (<li key={key}>{item}</li>))}
          </ul>}


        </div>
      </div>
    </div>
  );
};

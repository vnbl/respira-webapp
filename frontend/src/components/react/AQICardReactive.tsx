import * as React from "react";
import { getTextColor } from '../../utils';
import type { AQICard as CardType } from "../../data/cards";
import Smilling from "../../assets/emojis/smilling_face.svg"
import Beaming from "../../assets/emojis/beaming_face.svg"
import Medical from "../../assets/emojis/medical_face.svg"
import Skull from "../../assets/emojis/skull.svg"
import Cloud from "../../assets/emojis/cloud_face.svg"
import Anxious from "../../assets/emojis/anxious_face.svg"

export const AQICard = ({ card }: { card: CardType }) => {
  return (

    <div className={`bg-${card.color} w-full  rounded-xl p-10`}>
      <div className="flex flex-row w-full min-h-20">
        <div className="flex flex-col align-center justify-center mr-4">
          <img alt={card.icon.alt} src={card.icon.path.src}  height={60} width={60}/>
          {/* <p className="text-5xl text-center font-emoji">{card.icon}</p> */}
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
          <p
            className={`font-sans text-[1rem] text-${getTextColor(card.color) || "black"
              } `}
          >
            {card.description}
          </p>
        </div>
      </div>
    </div>
  );
};

import * as React from 'react'
import { getTextColor } from '../../utils'
import type { AQICard as CardType } from '../../data/cards'

export const AQICard = ({ card }: { card: CardType }) => {
  return (
    <div className={`bg-${card.color} w-full rounded-xl p-10`}>
      <div className="flex min-h-20 w-full flex-row">
        <div className="align-center mr-4 flex flex-1 flex-col justify-center">
          <p className="text-center font-emoji text-5xl">{card.icon}</p>
        </div>
        <div className="flex w-full flex-col justify-center">
          <div className="mb-2 flex flex-row flex-wrap">
            <h5
              className={`font-serif text-[1.25rem] font-bold text-${
                getTextColor(card.color) || 'black'
              } grow`}
            >
              {card.title}
            </h5>
            <h5
              className={`font-serif text-[1.25rem] font-bold text-${
                getTextColor(card.color) || 'black'
              }`}
            >
              {card.range[0]}-{card.range[1]}
            </h5>
          </div>
          <p
            className={`font-sans text-[1rem] text-${
              getTextColor(card.color) || 'black'
            } `}
          >
            {card.description}
          </p>
        </div>
      </div>
    </div>
  )
}

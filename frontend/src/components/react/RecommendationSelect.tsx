import {
  Tabs,
  TabsHeader,
  TabsBody,
  Tab,
  TabPanel,
} from "@material-tailwind/react";
import { AQI, type AQICard as CardType } from "../../data/cards";
import { getTextColor } from "../../utils";
import { AQICard } from "./AQICardReactive";
import React, { useMemo } from "react";
import { Select, Option } from "@material-tailwind/react";

export function RecommendationSelect() {
  const data = AQI
  const [selectedCard, setSelectedCard] = React.useState<any>(data[0].color)
  console.log(selectedCard)
  const card = useMemo(() => {
    console.log(AQI.find(val => val.color === selectedCard))
    return AQI.find(val => val.color === selectedCard)
  }, [selectedCard])
  return (
    <>
      <Select placeholder={"Seleccionar nivel"} label="Seleccionar nivel" value={card?.color} size="lg" labelProps={{ className: "font-bold md:hidden " }} className="block md:hidden bg-white text-md " onChange={(val) => setSelectedCard(val)}>
        {data.map((d) => (<Option  value={d.color}>{d.title}</Option>))}
      </Select>
      <div className="my-4">
        <AQICard card={card || AQI[0]} variant="recommendations" />
      </div>
    </>

  );
}
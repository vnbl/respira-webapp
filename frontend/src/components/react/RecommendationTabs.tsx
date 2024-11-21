import {
  Tabs,
  TabsHeader,
  TabsBody,
  Tab,
  TabPanel,
} from "@material-tailwind/react";
import { AQI } from "../../data/cards";
import { getTextColor } from "../../utils";
import { AQICard } from "./AQICardReactive";

export function RecommendationTabs() {
  const data = AQI

  return (
    <Tabs value={AQI[0].color} className="hidden md:block">
      <TabsHeader placeholder="HEADER"
        className="bg-transparent rounded-xl overflow-clip"

        indicatorProps={{
          className: "border-2 bg-transparent text-black fisrt:rounded-l-xl",
        }}>
        {data.map(({ slug, color }) => (
          <Tab key={color} value={color} placeholder={""} className={`bg-${color} min-h-16 text-${getTextColor(color)} font-semibold first:rounded-l-xl last:rounded-r-xl `}>
            {slug}
          </Tab>
        ))}
      </TabsHeader>
      <TabsBody placeholder={""}>
        {data.map((card) => (
          <TabPanel key={card.color} value={card.color}>
            <AQICard card={card} variant="recommendations"/>
          </TabPanel>
        ))}
      </TabsBody>
    </Tabs>
  );
}
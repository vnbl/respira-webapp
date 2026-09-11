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
import { useClientTranslations } from "../../i18n/client";
import { type UIKey } from "../../i18n/ui";

export function RecommendationTabs() {
  const data = AQI;
  const t = useClientTranslations();

  return (
    <Tabs value={AQI[0].color} className="hidden md:block">
      <TabsHeader
        placeholder="HEADER"
        className="bg-transparent rounded-xl overflow-visible items-stretch p-0"
        indicatorProps={{ className: "hidden" }}
      >
        {data.map(({ id, color }) => (
          <Tab
            key={color}
            value={color}
            placeholder={""}
            activeClassName="ring-2 ring-inset ring-black z-10"
            className={`bg-${color} basis-0 grow min-h-16 px-1 py-2 text-${getTextColor(color)} font-semibold first:rounded-l-xl last:rounded-r-xl text-[0.75rem] lg:text-[0.875rem] leading-tight hyphens-auto break-words`}
          >
            {t(`aqi.${id}.title` as UIKey)}
          </Tab>
        ))}
      </TabsHeader>
      <TabsBody placeholder={""}>
        {data.map((card) => (
          <TabPanel key={card.color} value={card.color}>
            <AQICard card={card} variant="recommendations" />
          </TabPanel>
        ))}
      </TabsBody>
    </Tabs>
  );
}

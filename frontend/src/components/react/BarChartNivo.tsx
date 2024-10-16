import React from 'react';

import { AQI_COLORS, AQI_RANGES } from '../../data/constants';
import { getAQIIndex } from '../../utils';
import { ResponsiveBar  } from '@nivo/bar';
import moment from "moment"

const getColorRange = (aqi =>  AQI_COLORS[getAQIIndex(aqi)])

const customTooltip = ({
    id,
    value,
    color
  }) => (<div class="bg-black p-2 rounded flex flex-col text-white font-serif">
                <p class="text-xs">AQI: {value}</p>
        </div>)

export const BarChart =  ({data}: any) => {

    return (
    <ResponsiveBar
        data={data}
        valueScale={{type: 'symlog'}}
        margin={{ top: 5, right: 5, bottom: 5, left: 5 }}
        padding={0.1}
        motionConfig="wobbly"
        keys={["value"]}
        indexBy='timestamp'
        enableGridY={false}
        colors={(datum) => getColorRange(datum.value)}
        enableLabel={false}
        indexScale={{ type: 'band', round: true }}
        axisLeft={null}
        minValue={0}
        maxValue={400}
        enableTotals={true} 
        totalsOffset={10}
        tooltip={(d) => customTooltip(d)}                 
        axisBottom={{
                            tickSize: 60,
                            tickPadding: 5,
                            tickRotation: 0,
                          }}    

                          

    />
)
}


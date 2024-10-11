import React from 'react';

import Plot from 'react-plotly.js';
import { AQI_COLORS, AQI_RANGES } from '../../data/constants';
import { getAQIIndex } from '../../utils';

const getColorRange = (aqis => aqis.map(aqi => AQI_COLORS[getAQIIndex(aqi)]))

export default ({xData, yData}:{xData:number[], yData:number[]}) => {
    console.log(yData)
    const colorRange = React.useMemo(() => getColorRange(yData), [yData])
    return (
    <Plot
        data={[
            { type: 'bar', x: xData, y: yData,   text: yData.map(String), textposition: 'outside',   marker:{

                color:colorRange
            
              }}
        ]}
        config={{ displayModeBar: false, displaylogo: false, scrollZoom: false, responsive: true , editable: false}}
        className='w-full h-full'
        layout={{ height:150,  xaxis:{type:'date', tickformat: '%I:%M<br>%p' } , yaxis: { type:'linear', showgrid: false, showticklabels: false, domain:[0,1/3]  }, showlegend: false, margin: { pad: 0, b: 40, l: 0, r: 0, t: 0 }, bargap:0.03 }}
        useResizeHandler={true}
    />

)
}


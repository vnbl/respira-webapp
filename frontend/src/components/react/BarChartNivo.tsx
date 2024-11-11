import React from 'react'

import { AQI_COLORS } from '../../data/constants'
import { getAQIIndex } from '../../utils'
import { ResponsiveBar } from '@nivo/bar'
import { timeFormat } from 'd3-time-format'
import { scaleTime } from 'd3-scale'
import { BarItem } from './BarItem'

const getColorRange = (aqi: number) => AQI_COLORS[getAQIIndex(aqi)]

const customTooltip = ({ value }: { value: number }) => (
  <div className="flex flex-col rounded bg-black p-2 font-serif text-white">
    <p className="text-xs">{value}</p>
  </div>
)

export const BarChart = ({ data }: any) => {
  const maxValue = React.useMemo(() => {
    return Math.max(...data.map((d: any) => d.value))
  }, [data])

  const formatter = timeFormat('%I %p')
  const timeScaleTicks: string[] = React.useMemo(() => {
    const scale = scaleTime().domain([
      new Date(data[0].timestamp),
      new Date(data[data.length - 1].timestamp),
    ])
    const ticks = scale.ticks(data.length > 6 ? 6 : 10)
    return ticks.map((tick) => formatter(tick))
  }, data)
  // const TopLine = ({series, slices}: BarCustomLayerProps<Number>) => {
  //   return (
  //     <g>
  //       {rects.map((rect) => (
  //         <rect
  //           key={rect.id}
  //           x={rect.x}
  //           y={0}
  //           width={rect.width}
  //           height={rect.height}
  //           style={{
  //             fill: '#fafafa',
  //           }}
  //         />
  //       ))}
  //     </g>
  //   )
  // }

  return (
    <ResponsiveBar
      data={data}
      motionConfig="wobbly"
      keys={['value']}
      indexBy="timestamp"
      padding={0.05}
      barComponent={BarItem}
      enableGridY={false}
      colors={(datum) => getColorRange(datum.value || 0)}
      enableLabel={false}
      margin={{
        top: maxValue > 300 ? 30 : 15,
        right: 0,
        bottom: 25,
        left: 0,
      }}
      axisLeft={null}
      minValue={0}
      maxValue={maxValue}
      enableTotals={true}
      totalsOffset={10}
      tooltip={(d) => customTooltip(d)}
      valueScale={{
        type: 'symlog',
        min: 0,
        max: 400,
      }}
      valueFormat={(value) => Math.round(value).toString()}
      axisBottom={{
        tickSize: 5,
        tickPadding: 5,
        tickRotation: 0,
        format: (val) => {
          const formatted = formatter(new Date(val))
          return timeScaleTicks.includes(formatted) ? formatted : ''
        },
      }}
      theme={{
        text: {
          fontSize: 12,
          fill: '#A1A1A1',
        },
        axis: {
          domain: {
            line: {
              stroke: '#ECECEC',
              strokeWidth: 2,
            },
          },
        },
      }}
    />
  )
}

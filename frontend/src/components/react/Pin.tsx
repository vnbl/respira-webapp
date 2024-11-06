import * as React from "react";

const pinStyle = {
  cursor: "pointer",
  fill: "#d00",
  stroke: "none",
};

const Pin = ({ size = 100, fill, value } : {size?:number, fill: string, value:number}) => {
  return (
    <svg height={size} width={100} viewBox="0 0 102 103" style={pinStyle}>
      <g filter="url(#filter0_d_247_35929)">
        <circle
          cx="51"
          cy="48"
          r="32.2143"
          stroke="#0F0F0F"
          strokeWidth="5.57143"
          fill={fill}
        />
        <text
          x="50%"
          y="55%"
          textAnchor="middle"
          stroke="#0F0F0F"
          fill="#0F0F0F"
          fontSize="1.5rem"
        >
          {value}
        </text>
      </g>
    </svg>
  );
};

export default React.memo(Pin);

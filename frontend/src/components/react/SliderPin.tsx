import * as React from "react";

const style = {
  cursor: "pointer",
  fill: "none",
  stroke: "none",
};

const Pin = ({ size = 56, value, fill }) => {
  return (
    <svg height={size} viewBox="0 0 45 56" style={style}>
      <g filter="url(#filter0_d_328_13963)">
        <path
          d="M22.606 0C12.6474 0 4.60596 8.10666 4.60596 18.0267C4.60596 32.8 22.606 48 22.606 48C22.606 48 40.606 32.8 40.606 18.0267C40.606 8.10666 32.5645 0 22.606 0Z"
          fill={fill}
        />
      </g>
      <rect x="10.606" y="6" width="25" height="26" rx="12.5" fill="white" />
      <text
        x="52.5%"
        y="40%"
        textAnchor="middle"
        stroke="#535353"
        fill="#535353"
        fontSize="0.8rem"
      >
        {Math.round(value)}
      </text>
      <defs>
        <filter
          id="filter0_d_328_13963"
          x="0.605957"
          y="0"
          width="44"
          height="56"
          filterUnits="userSpaceOnUse"
          colorInterpolationFilters="sRGB"
        >
          <feFlood floodOpacity="0" result="BackgroundImageFix" />
          <feColorMatrix
            in="SourceAlpha"
            type="matrix"
            values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 127 0"
            result="hardAlpha"
          />
          <feOffset dy="4" />
          <feGaussianBlur stdDeviation="2" />
          <feComposite in2="hardAlpha" operator="out" />
          <feColorMatrix
            type="matrix"
            values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.25 0"
          />
          <feBlend
            mode="normal"
            in2="BackgroundImageFix"
            result="effect1_dropShadow_328_13963"
          />
          <feBlend
            mode="normal"
            in="SourceGraphic"
            in2="effect1_dropShadow_328_13963"
            result="shape"
          />
        </filter>
      </defs>
    </svg>
  );
};

export default React.memo(Pin);

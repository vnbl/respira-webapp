import { isBackendAvailable } from './store/store';

import {AQI_COLORS} from "./data/constants"

export const getAQIIndex = (aqi: number): number => {
    const ranges: [number, number][] = [[0, 50], [51, 100], [101, 150], [151, 200], [201, 300], [301, 400]];
    // If value is out of range the default color is the last one
    let AQIIndex = 5;

    if(!aqi || aqi <0){
        throw SyntaxError("getAQIIndex: 'aqi' is not defined")
    }
    if(aqi<0){
        throw SyntaxError("getAQIIndex: 'aqi' is not a valid number; must be > 0")
    }
    for( const [index, r] of ranges.entries()) {
        if(aqi>=r[0] && aqi<=r[1]){
            AQIIndex=index
            break;
        }
    }
    return AQIIndex
}

export const getColorRange = (aqi) => AQI_COLORS[getAQIIndex(aqi)];

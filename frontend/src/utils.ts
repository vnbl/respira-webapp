
import {AQI_COLORS} from "./data/constants"

export const getAQIIndex = (aqi: number): number => {
    const ranges: [number, number][] = [[0, 50], [51, 100], [101, 150], [151, 200], [201, 300], [301, 400]];
    // If value is out of range the default color is the last one
    let AQIIndex = 5;

    if(!aqi){
        throw SyntaxError("getAQIIndex: 'aqi' is not defined")
    }
    if(aqi<0){
        throw SyntaxError("getAQIIndex: 'aqi' is not a valid number; must be > 0")
    }
    const roundedAqi = Math.round(aqi)
    for( const [index, r] of ranges.entries()) {
        if(roundedAqi>=r[0] && roundedAqi<=r[1]){
            AQIIndex=index
            break;
        }
    }
    return AQIIndex
}

export const getColorRange = (aqi:number) => AQI_COLORS[getAQIIndex(aqi)];


export const getTextColor = (bg: string) => {
    const darks = ["aqi-red-dark", "aqi-purple-dark", "aqi-vermellion-dark"]
    if(darks.includes(bg)) {
        return "white"
    }
    return "black"
}

import { isBackendAvailable } from './store/store';

export const backendHealthCheck = async () => {
    try {
        const response = await fetch(import.meta.env.BACKEND_URL + '/health');
        isBackendAvailable.set(true)
        if(response.status !== 200) {
            throw Error()
        }
    } catch (_) {
        console.log("Backend not available")
        isBackendAvailable.set(false)
    }
}


export const getAQIIndex = (aqi: number) => {
    const ranges: [number, number][] = [[0, 50], [51, 100], [101, 150], [151, 200], [201, 300], [301, 400]];
    let AQIIndex = undefined;
    for( const [index, r] of ranges.entries()) {
        if(aqi>=r[0] && aqi<=r[1]){
            AQIIndex=index
            break;
        }
    }
    if(AQIIndex === undefined) {
        throw RangeError("AQI value out of range")
    }
    return AQIIndex
}
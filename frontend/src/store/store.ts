import { atom, computed, task } from 'nanostores';
import { backendHealthCheck  } from '../utils';

type STATION = {
    id: number,
    name: string,
    coordinates: string[],
    is_station_on: boolean,
    
}

export const isBackendAvailable = computed( [], () => task(async () => {
    return backendHealthCheck();
}))


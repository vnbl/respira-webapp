import { atom, computed, task } from 'nanostores';
import { backendHealthCheck  } from '../utils';
import { shared } from '@it-astro:request-nanostores';

type STATION = {
    id: number,
    name: string,
    coordinates: string[],
    is_station_on: boolean,
    
}


export const isBackendAvailable = shared('isBackendAvailable', atom([]))
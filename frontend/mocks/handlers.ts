import { http, HttpResponse } from 'msw'
import moment from "moment"
import {DateTime} from "luxon"

export const handlers = [
    http.get('http://localhost:7000/api/health', () => {
        return new HttpResponse(null, {
            status: 200 
        })
    }),
    http.get('http://localhost:7000/api/map', ({ request }) => {
        const url = new URL(request.url)
        const entity = url.searchParams.get('entity')
        if (entity === "region") {
            return HttpResponse.json({
                aqi: 200,
                forecast_6h: [
                    {
                        aqi: 40,
                        time: DateTime.now().toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 120,
                        time: DateTime.now().plus({hours: 1}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 180,
                        time:  DateTime.now().plus({hours: 2}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 230,
                        time:  DateTime.now().plus({hours: 3}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 280,
                        time:  DateTime.now().plus({hours: 4}).toFormat("yyyy-MM-dd TT")
                    },     {
                        aqi: 320,
                        time:  DateTime.now().plus({hours: 5}).toFormat("yyyy-MM-dd TT")
                    }
                ],
                forecast_12h: [
                    {
                        aqi: 40,
                        time: DateTime.now().toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 120,
                        time: DateTime.now().plus({hours: 1}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 180,
                        time:  DateTime.now().plus({hours: 2}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 230,
                        time:  DateTime.now().plus({hours: 3}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 280,
                        time:  DateTime.now().plus({hours: 4}).toFormat("yyyy-MM-dd TT")
                    },   
                    {
                        aqi: 320,
                        time:  DateTime.now().plus({hours: 5}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 80,
                        time:  DateTime.now().plus({hours: 6}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 80,
                        time:  DateTime.now().plus({hours: 7}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 80,
                        time:  DateTime.now().plus({hours: 8}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 80,
                        time:  DateTime.now().plus({hours: 9}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 80,
                        time:  DateTime.now().plus({hours: 10}).toFormat("yyyy-MM-dd TT")
                    },
                    {
                        aqi: 80,
                        time:  DateTime.now().plus({hours: 11}).toFormat("yyyy-MM-dd TT")
                    },
                ],
            })
        }
        return HttpResponse.json({
            aqi: 200,
            forecast_6h:  [
                {
                    aqi: 100,
                    time: moment()
                },
                {
                    aqi: 83,
                    time: moment().add(2, 'hours')
                },
                {
                    aqi: 250,
                    time: moment().add(3, 'hours')
                },
                {
                    aqi: 300,
                    time: moment().add(4, 'hours')
                },
                {
                    aqi: 40,
                    time: moment().add(5, 'hours')
                },     {
                    aqi: 2,
                    time: moment().add(6, 'hours')
                }
            ],
            forecast_12h: [
                {
                    aqi: 200,
                    time: moment().add(3, 'hour')
                }
            ]
        })

    }),


]
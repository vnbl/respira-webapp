export type MenuItem = {
    title: string;
    subtitle?: string;
    route: string | MenuItem[]
    id: string
    type?: 'route' | 'modal'
}

const stations : MenuItem[] = [
    {title: "Estación 1", subtitle: "Campus de la UNA", route:"estacion-1", id:"estacion-1"},
    {title: "Estación 2", subtitle: "Zona Multiplaza", route:"estacion-2", id:"estacion-2"},
    {title: "Estación 3", subtitle: "Acceso Sur", route:"estacion-3", id:"estacion-3"},
    {title: "Estación 4", subtitle: "Primero de Marzo Y Perón", route:"estacion-4", id:"estacion-4"},
    {title: "Estación 5", subtitle: "Villa Morra", route:"estacion-5", id:"estacion-5"},
    {title: "Estación 6", subtitle: "Barrio Jara", route:"estacion-6", id:"estacion-6"},
    {title: "Estación 7", subtitle: "San Roque", route:"estacion-7", id:"estacion-7"},
    {title: "Estación 8", subtitle: "Centro de Asunción", route:"estacion-8", id:"estacion-8"},    
    {title: "Estación 9", subtitle: "Ñu Guasu", route:"estacion-9", id:"estacion-9"},
    {title: "Estación 10", subtitle: "Botánico", route:"estacion-10", id:"estacion-10"},
    {title: "Media General", subtitle: "Todo Asunción", route:"media-general", id:"media-general"},
]

export const menu: MenuItem[] = [
    {title: 'Recibir alertas', route: '/alertas', id:'alerts', type: 'modal'},
    {title: 'Contacto', route: '/contacto', id:'contact'},
    {title: 'Sobre nosotros', route: '/nosotros', id:'us'},
    {title: 'Recursos', route: '/recursos', id:'research'},
    {title: 'Datos',route: stations, id:'data'}
]
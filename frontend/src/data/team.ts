import type { Image } from "./images";

import  Fernanda from "../assets/team/fernanda_carles.png"
import  Alvaro from "../assets/team/alvaro_machuca.png"
import Sol from "../assets/team/sol_benitez.png"
import Liliana from "../assets/team/liliana_estigarribia.png"
import Carlos from "../assets/team/carlos_sauer.png"
import Carolina from "../assets/team/carolina_recalde.png"
import Diego from "../assets/team/diego_stalder.png"
import Fabian from "../assets/team/fabian_bozzolo.png"
import Luis from "../assets/team/luis_bernal.png"
import Clara from "../assets/team/clara_berendsen.png"

type TEAM_CARD = {
    name: string;
    title: string;
    image: Omit<Image, "alt">
}


export const TEAM : TEAM_CARD []= [
    {
        name: "Fernanda Carles",
        title: "Project Leader, Data Scientist and Developer",
        image: {
            path: Fernanda
        }
    },
    {
        name: "Álvaro Machuca",
        title: "Software Architect, Developer",
        image: {
            path: Alvaro
        }
    },
    {
        name: "Soledad Benítez",
        title: "Product Designer",
        image: {
            path: Sol
        }
    },
    {
        name: "Clara Berendsen",
        title: "Frontend Developer",
        image: {
            path: Clara
        }
    },
    {
        name: "Liliana Estigarribia",
        title: "Project Coordinator",
        image: {
            path: Liliana
        }
    },
    {
        name: "Fabián Bozzolo",
        title: "Comunicación",
        image: {
            path: Fabian
        }
    },      
    {
        name: "Diego Stalder",
        title: "Data Science Advisor - FIUNA",
        image: {
            path: Diego
        }
    },  
    {
        name: "Carlos Sauer",
        title: "Data Science Advisor - FIUNA",
        image: {
            path: Carlos
        }
    },  
    {
        name: "Luis Bernal",
        title: "Database Manager - FIUNA",
        image: {
            path: Luis
        }
    }, 
    {
        name: "Carolina Recalde",
        title: "Especialista en Monitoreo Ambiental - FIUNA",
        image: {
            path: Carolina
        }
    }, 
]
import type { Image } from "./images"

import Smilling from "../assets/emojis/smilling_face.svg"
import Beaming from "../assets/emojis/beaming_face.svg"
import Medical from "../assets/emojis/medical_face.svg"
import Skull from "../assets/emojis/skull.svg"
import Cloud from "../assets/emojis/cloud_face.svg"
import Anxious from "../assets/emojis/anxious_face.svg"

export type AQICard = {
    color: string,
    icon: Image,
    title: string,
    range:[number, number],
    description: string
}

export const AQI :AQICard[] = [
    {
        color: "aqi-green-dark",
        icon: {
            alt: "Beaming face",
            path: Beaming,
        },
        title: "Bueno",
        range: [0,50],
        description: "¡Es un día excelente para realizar actividades al aire libre!"
    },
    {
        color: "aqi-yellow-dark",
        icon: {
            alt: "Smilling face",
            path: Smilling,
        },
        title: "Moderado",
        range: [51,100],
        description: "Las personas sensibles pueden presentar síntomas como tos o dificultad para respirar y deben seguir las precauciones habituales pero es un buen día para realizar actividades al aire libre."
    },
    {
        color: "aqi-orange-dark",
        icon: {
            alt: "Medical mask face",
            path: Medical,
        },
        title: "Insalubre para grupos sensibles",
        range: [101,150],
        description: "Las personas sensibles pueden presentar síntomas y deben seguir las precauciones habituales para manejar."
    },
    {
        color: "aqi-red-dark",
        icon: {
            alt: "Cloud face",
            path: Cloud,
        },
        title: "Insalubre",
        range: [151,200],
        description: "Todos debemos limitar actividades al aire libre. Las personas sensibles deben evitar las actividades al aire libre y reprogramar cualquier evento al aire libre."
    },
    {
        color: "aqi-purple-dark",
        icon: {
            alt: "Anxious face",
            path: Anxious,
        },
        title: "Muy Insalubre",
        range: [201,300],
        description: "Traslade a un lugar cerrado las actividades innecesarias. Todos debemos evitar actividades al aire libre extenuantes y prolongadas. Reprograme actividades al aire libre. "
    },
    {
        color: "aqi-vermellion-dark",
        icon: {
            alt: "Skull face",
            path: Skull,
        },
        title: "Peligroso",
        range: [301,400],
        description: "Todos debemos evitar las actividades al aire libre innecesarias por completo. Permanezca adentro y mantenga un nivel de actividad bajo."
    }
] 
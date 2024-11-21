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
    range: [number, number],
    description: string,
    slug: string,
    recommendations: string[]
}

export const AQI: AQICard[] = [
    {
        color: "aqi-green-dark",
        icon: {
            alt: "Beaming face",
            path: Beaming,
        },
        title: "Bueno",
        slug: "Bueno",
        range: [0, 50],
        description: "¡Es un día excelente para realizar actividades al aire libre!",
        recommendations: ["Ventilá habitaciones y oficinas.", "Disfrutá de actividades al aire libre.", "Aprovechá para hacer ejercicio."]
    },
    {
        color: "aqi-yellow-dark",
        icon: {
            alt: "Smilling face",
            path: Smilling,
        },
        title: "Moderado",
        slug: "Moderado",
        range: [51, 100],
        description: "Las personas sensibles pueden presentar síntomas como tos o dificultad para respirar y deben seguir las precauciones habituales pero es un buen día para realizar actividades al aire libre.",
        recommendations: ["Grupos sensibles: reducí la actividad física si presentás síntomas.", "Prestá atención a la tos, dificultad para respirar o irritación ocular.", "Evitá zonas con alta contaminación."]
    },
    {
        color: "aqi-orange-dark",
        icon: {
            alt: "Medical mask face",
            path: Medical,
        },
        title: "Insalubre para grupos sensibles",
        slug: "Insalubre",
        range: [101, 150],
        description: "Las personas sensibles pueden presentar síntomas y deben seguir las precauciones habituales para manejar.",
        recommendations: ["Grupos sensibles: usá tapabocas y llevá medicamentos si es necesario salir.", "Evitá esfuerzos prolongados al aire libre.", "Evitá esfuerzos prolongados al aire libre."]
    },
    {
        color: "aqi-red-dark",
        icon: {
            alt: "Cloud face",
            path: Cloud,
        },
        title: "Insalubre",
        slug: "Insalubre",
        range: [151, 200],
        description: "Todos debemos limitar actividades al aire libre. Las personas sensibles deben evitar las actividades al aire libre y reprogramar cualquier evento al aire libre.",
        recommendations: ["Grupos sensibles: evitá cualquier actividad al aire libre.", "Si tenés que salir, usá tapabocas.", "Mantené tu hogar u oficina bien sellados para evitar el aire contaminado."]
    },
    {
        color: "aqi-purple-dark",
        icon: {
            alt: "Anxious face",
            path: Anxious,
        },
        title: "Muy Insalubre",
        slug: "Muy Insalubre",
        range: [201, 300],
        description: "Traslade a un lugar cerrado las actividades innecesarias. Todos debemos evitar actividades al aire libre extenuantes y prolongadas. Reprograme actividades al aire libre. ",
        recommendations: ["Todos: evitá actividades al aire libre.", "Si es necesario salir, usá tapabocas y tené medicamentos a mano.", "Consultá a un médico si los síntomas se agravan."]
    },
    {
        color: "aqi-vermellion-dark",
        icon: {
            alt: "Skull face",
            path: Skull,
        },
        title: "Peligroso",
        slug: "Peligroso",
        range: [301, 400],
        description: "Todos debemos evitar las actividades al aire libre innecesarias por completo. Permanezca adentro y mantenga un nivel de actividad bajo.",
        recommendations: ["Todos: evitá la exposición al aire contaminado.", "Prestá atención a los síntomas respiratorios y consultá a un médico si es necesario."]
    }
] 
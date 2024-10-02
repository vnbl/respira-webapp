export type AIQCard = {
    color: string,
    icon: string,
    title: string,
    range:[number, number],
    description: string
}

export const AIQ :AIQCard[] = [
    {
        color: "aiq-green-dark",
        icon: "😁",
        title: "Bueno",
        range: [0,50],
        description: "¡Es un día excelente para realizar actividades al aire libre!"
    },
    {
        color: "aiq-yellow-dark",
        icon: "🙂",
        title: "Moderado",
        range: [51,100],
        description: "Las personas sensibles pueden presentar síntomas como tos o dificultad para respirar y deben seguir las precauciones habituales pero es un buen día para realizar actividades al aire libre."
    },
    {
        color: "aiq-orange-dark",
        icon: "😷",
        title: "Insalubre para grupos sensibles",
        range: [101,150],
        description: "Las personas sensibles pueden presentar síntomas y deben seguir las precauciones habituales para manejar."
    },
    {
        color: "aiq-red-dark",
        icon: "😶‍🌫️",
        title: "Insalubre",
        range: [151,200],
        description: "Todos debemos limitar actividades al aire libre. Las personas sensibles deben evitar las actividades al aire libre y reprogramar cualquier evento al aire libre."
    },
    {
        color: "aiq-purple-dark",
        icon: "😰",
        title: "Muy Insalubre",
        range: [201,300],
        description: "Traslade a un lugar cerrado las actividades innecesarias. Todos debemos evitar actividades al aire libre extenuantes y prolongadas. Reprograme actividades al aire libre. "
    },
    {
        color: "aiq-vermellion-dark",
        icon: "💀",
        title: "Peligroso",
        range: [301,400],
        description: "Todos debemos evitar las actividades al aire libre innecesarias por completo. Permanezca adentro y mantenga un nivel de actividad bajo."
    }
] 
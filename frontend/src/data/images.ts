import Image from 'astro/components/Image.astro'

import Heart from '../assets/icons/heart_icon.svg'
import Lung from '../assets/icons/lung_icon.svg'
import Flower from '../assets/icons/flower_icon.svg'
import Medicine from '../assets/icons/medicine_icon.svg'

import Facebook from '../assets/icons/facebook_icon.svg'
import Instagram from '../assets/icons/instagram_icon.svg'
import Telegram from '../assets/icons/telegram_icon.svg'

import Fiuna from '../assets/logos/fiuna.svg'
import Mozilla from '../assets/logos/mozilla.svg'
import GirlsCode from '../assets/logos/girls_code.svg'

import FiunaBlack from '../assets/logos/fiuna_black.svg'
import MozillaBlack from '../assets/logos/mozilla_black.svg'
import GirlsCodeBlack from '../assets/logos/girls_code_black.svg'

import Epa from '../assets/logos/epa.svg'
import Pho from '../assets/logos/pho.svg'
import Who from '../assets/logos/who.svg'
import AireLibre from '../assets/logos/aire_libre.svg'

import { INSTAGRAM_URL, FACEBOOK_URL, TELEGRAM_URL } from './constants'

export type Image = {
  alt: string
  path: ImageMetadata
  class?: string
}

export type Link = {
  text: string
  link: string
}

export const HOME_IMAGES: Image[] = [
  {
    alt: 'Heart icon',
    path: Heart,
    class: 'h-14 w-14',
  },
  {
    alt: 'Lung icon',
    path: Lung,
    class: 'h-14 w-14',
  },
  {
    alt: 'Flower icon',
    path: Flower,
    class: 'h-14 w-14',
  },
  {
    alt: 'Medicine icon',
    path: Medicine,
    class: 'h-14 w-14',
  },
]

export const FOOTER_IMAGES: Image[] = [
  {
    alt: 'Facultad de ingenieria Logo',
    path: Fiuna,
  },
  {
    alt: 'Mozilla logo',
    path: Mozilla,
  },
  {
    alt: 'Girls code logo',
    path: GirlsCode,
  },
]

export const ORGANIZATIONS: Image[] = [
  {
    alt: 'Facultad de ingenieria Logo',
    path: FiunaBlack,
  },
  {
    alt: 'Mozilla logo',
    path: MozillaBlack,
  },
  {
    alt: 'Girls code logo',
    path: GirlsCodeBlack,
  },
]

export const EXTERNAL_RESOURCES_IMAGES: (Image & Link)[] = [
  {
    alt: 'EPA Logo',
    path: Epa,
    text: 'Guía de la calidad del aire. Agencia de Protección Ambiental de Estados Unidos',
    link: 'https://www.airnow.gov/sites/default/files/2018-05/air-quality-guide_ozone_SPA.pdf',
  },
  {
    alt: 'Panamerican Health Organization Logo',
    path: Pho,
    text: '(OPS) Organización Panamericana de la Salud',
    link: 'https://www.paho.org/es',
  },

  {
    alt: 'World Health Organization Logo',
    path: Who,
    text: '(OMS) Organización Mundial de la Salud',
    link: 'https://www.who.int/es',
  },
  {
    alt: 'Aire Libre Logo',
    path: AireLibre,
    text: 'Aire Libre',
    link: 'https://airelib.re/',
  },
]

export const SOCIAL_MEDIA_IMAGES: Omit<Image & Link, 'text'>[] = [
  {
    alt: 'Telegram Icon',
    path: Telegram,
    link: TELEGRAM_URL,
  },
  {
    alt: 'Instagram Icon',
    path: Instagram,
    link: INSTAGRAM_URL,
  },
  {
    alt: 'Facebook Icon',
    path: Facebook,
    link: FACEBOOK_URL,
  },
]

export const TWITTER_URL="https://twitter.com/respirapy"
export const TELEGRAM_URL ="https://t.me/proyectorespira" 
export const FACEBOOK_URL="https://www.facebook.com/proyectorespirapy"
export const INSTAGRAM_URL= "https://www.instagram.com/proyectorespirapy"
export const CONTACT_MAIL="airefiuna@ing.una.py"
export const GITHUB_URL="https://github.com/vnbl/Mozilla-Aire"



export const AQI_RANGES : [number, number][] = [[0, 50], [51, 100], [101, 150], [151, 200], [201, 300], [301, 400]];
export const AQI_COLORS : string[] = ["#AFFAAF", "#FFEB7F","#FBC189","#F27474","#B179B6","#98334F"];

export const EXCLUDED_STATIONS: number[] = [101]

export const BACKEND_URL= import.meta.env.PUBLIC_BACKEND_URL 

export const BASE_URL = import.meta.env.SITE 

export const TELEGRAM_SHARE =`https://telegram.me/share/url?url=${BASE_URL}`
export const TWITTER_SHARE = `http://twitter.com/share?text="Mira la calidad del aire en Asunción en...${BASE_URL}&url=${BASE_URL}`
export const FACEBOOK_SHARE = `https://www.facebook.com/dialog/share?display=popup&href=${"dev.proyectorespira.net"}&redirect_uri=${"dev.proyectorespira.net"}`

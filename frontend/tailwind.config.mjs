/** @type {import('tailwindcss').Config} */

export default {
	content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
	theme: {
		fontFamily: {
			sans: ['Open Sans Variable', 'sans-serif'],
			serif:['Merriweather'],
			emoji:['Inter Variable']
		},
		borderWidth: {
      DEFAULT: '1px',
      '0': '0',
      '2': '2px',
      '3': '3px',
      '4': '4px',
      '6': '6px',
      '8': '8px',
    },
		colors: {
			base: '#F0ECEA',
			basedark: '#afa29c',
			green: '#91BE7B',
			light_green: '#C7D2A7',
			white: '#FFF',
			black: '#000',
			gray: "#535353",
			lightgray:"#A1A1A1",
			cyan: '#8ADBE6',
			["bg-gray"]: '#DBD3D0',
			aqi: {
				green: {
					dark: '#AFFAAF',
					light: '#107710' 
				},
				yellow: {
					dark: '#FFE663',
					light: '#FFEB7F' 
				},
				orange: {
					dark: '#F9A756',
					light: '#FBC189' 
				},
				red: {
					dark: '#ED3939',
					light: '#F27474' 
				},
				purple: {
					dark: '#8F3F97',
					light: '#B179B6' 
				},
				vermellion: {
					dark: '#7E0023',
					light: '#98334F' 
				},
			}
		},
		extend: {},
	},
	plugins: [],
}

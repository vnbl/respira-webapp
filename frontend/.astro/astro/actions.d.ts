declare module "astro:actions" {
	type Actions = typeof import("/home/claraberendsen/Mozilla-Aire/frontend/src/actions")["server"];

	export const actions: Actions;
}
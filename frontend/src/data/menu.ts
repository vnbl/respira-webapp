import { loadingStations, stations } from "../store/map";
import { GITHUB_URL } from "./constants";

export type DynamicMenuItem = {
  store: any;
  loading: any;
  baseRoute: string;
  titleKey: string;
  subtitleKey: string
}

export type MenuItem = {
  title: string;
  subtitle?: string;
  route: string | MenuItem[];
  id: string;
  type?: "route" | "modal";
};

export type MenuItemDropdown = {
  title: string;
  subtitle?: string;
  route: DynamicMenuItem;
  id: string;
  type?: "dropdown";
};




export const menu: (MenuItem | MenuItemDropdown)[] = [
  { title: "Recibir alertas", route: "/alertas", id: "alerts", type: "modal" },
  { title: "Contacto", route: "/contacto", id: "contact" },
  { title: "Sobre nosotros", route: "/nosotros", id: "us" },
  { title: "Recursos", route: "/recursos", id: "research" },
  {
    title: "Datos", route: {
      store: stations,
      loading: loadingStations,
      baseRoute: "/datos",
      titleKey: "id",
      subtitleKey: "name"
    }, id: "data", type: "dropdown" },
];

export const FOOTER_MENU: MenuItem[] = [
  {
    title: "Recursos",
    id: "resource-menu",
    route: [
      {
        title: "Mapa",
        route: "/",
        id: "map",
      },
      {
        title: "Investigaciones y recursos",
        route: "/recursos",
        id: "research",
      },
      {
        title: "Github",
        route: GITHUB_URL,
        id: "github"
      },
    ],
  },
  {
    title: "El proyecto",
    id: "project-menu",
    route: [
      {
        title: "Sobre el proyecto",
        route: "/nosotros",
        id: "us",
      },
      {
        title: "Contacto",
        route: "/contacto",
        id: "contact",
      },
    ],
  },
];

import astroFormsMiddleware from "@astro-utils/forms";
import {sequence} from "astro/middleware";

export const onRequest = sequence(astroFormsMiddleware());
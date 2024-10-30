import { defineAction, z } from "astro:actions";

export const server = {
  sendMail: defineAction({
    accept: "form",
    input: z.object({
      email: z.string().email(),
      name: z.string(),
      lastname: z.string().optional(),
      motive: z.string(),
      message: z.string()
    }),
    handler: async ({ email, name, lastname, motive, message }) => {
      console.log({ email, name, lastname, motive, message })
      // call a mailing service, or store to a database
      return { success: true };
    },
  }),
};
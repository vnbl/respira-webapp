import { defineAction } from "astro:actions";
import { z } from 'astro:schema';
import { Resend } from 'resend';
import { BASE_URL, CONTACT_MAIL } from "../data/constants";
import { Email } from '../components/react/ContactEmail';
const resend = new Resend(import.meta.env.SMTP_KEY);

const formInput = z.object({
  email: z.string().email(),
  name: z.string(),
  lastname: z.string().optional(),
  motive: z.string(),
  message: z.string()
})

export type EmailInput = z.infer<typeof formInput>

const sendMail = async (values: EmailInput) => {
  return resend.emails.send({
    from:import.meta.env.SMTP_SENDER,
    to: ['delivered@resend.dev', CONTACT_MAIL],
    subject: `[${BASE_URL}] ${values.motive} `,
    react: Email(values),
  });


}
export const server = {
  sendMail: defineAction({
    accept: "form",
    input: formInput,
    handler: async (values) => sendMail(values)
  }),
};
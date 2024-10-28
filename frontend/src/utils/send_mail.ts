import nodemailer from 'nodemailer';

const sendMail = async () => {
  const transporter = nodemailer.createTransport({
    host: 'smtp.resend.com',
    secure: true,
    port: 465,
    auth: {
      user: 'resend',
      pass: import.meta.env.STMP_KEY,
    },
  });

  const info = await transporter.sendMail({
    from: 'test@resend.dev',
    to: 'claraberendsen@gmail.com',
    subject: 'Hello World',
    html: '<strong>It works!</strong>',
  });

  console.log('Message sent: %s', info.messageId);
}

export {sendMail}
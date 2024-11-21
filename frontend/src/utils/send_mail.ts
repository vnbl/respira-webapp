import nodemailer from 'nodemailer';

const sendMail = async () => {
  const transporter = nodemailer.createTransport({
    host: import.meta.env.SMTP_HOST,
    secure: true,
    port: 465,
    auth: {
      user: import.meta.env.SMTP_USER,
      pass: import.meta.env.SMTP_KEY,
    },
  });

  const info = await transporter.sendMail({
    from: import.meta.env.SMTP_SENDER,
    to: 'claraberendsen@gmail.com',
    subject: 'Hello World',
    html: '<strong>It works!</strong>',
  });

  console.log('Message sent: %s', info.messageId);
}

export {sendMail}
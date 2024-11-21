import * as React from 'react';
import {
  Body,
  Button,
  Container,
  Head,
  Html,
  Img,
  Link,
  Preview,
  Section,
  Text,
} from "@react-email/components";
import type { EmailInput } from '../../actions/index.tsx';
import { BASE_URL } from '../../data/constants.ts';

export function Email(props: EmailInput) {
  const { name, lastname, motive, message, email } = props;

  return (
    <Html>
      <Head />
      <Preview>Nueva consulta</Preview>
      <Body style={main}>
        <Container style={container}>
          <Img
            src={`${BASE_URL}/favicon.png`}
            width="40"
            height="33"
            alt="Respira"
          />
          <Section>
            <Text style={textBold}>Nombre</Text>
            <Text style={text}>{name} {lastname}</Text>
            <Text style={textBold}>Contacto</Text>
            <Text style={text}>{email}</Text>
            <Text style={textBold}>Motivo de consulta</Text>
            <Text style={text}>{motive}</Text>
            <Text style={textBold}>Mensaje</Text>
            <Text style={text}>{message}</Text>
          </Section>
        </Container>
      </Body>
    </Html>
  );
}


const main = {
  backgroundColor: "#f6f9fc",
  padding: "10px 0",
};

const container = {
  backgroundColor: "#ffffff",
  border: "1px solid #f0f0f0",
  padding: "45px",
};

const text = {
  fontSize: "16px",
  fontFamily:
    "'Open Sans', 'HelveticaNeue-Light', 'Helvetica Neue Light', 'Helvetica Neue', Helvetica, Arial, 'Lucida Grande', sans-serif",
  fontWeight: "300",
  color: "#404040",
  lineHeight: "26px",
};
const textBold = {
  fontSize: "16px",
  fontFamily:
    "'Open Sans', 'HelveticaNeue-Light', 'Helvetica Neue Light', 'Helvetica Neue', Helvetica, Arial, 'Lucida Grande', sans-serif",
  fontWeight: "600",
  color: "#404040",
  lineHeight: "26px",
};
export default Email;
// Copy for the institutional dashboard (RES-328).
//
// Kept out of `i18n/ui.ts` on purpose: that dictionary is the public site's,
// and this one is large, feature-specific and edited far more often. Holding it
// apart keeps the two diffs from colliding.
//
// Trilingual like `ui.ts`: every key must exist in `es`, `en` and `pt`, and
// `useInstitutionCopy(lang)` falls back to Spanish for anything missing, so a
// half-finished translation never renders an empty string.
//
// Voice: the Spanish is Paraguayan voseo, second person, no jargon. Portuguese
// uses "você" and English plain second person — the same register, not a
// literal word-for-word carry-over.

import { DEFAULT_LANG, type Lang } from "./config";

const es = {
  // --- Shell ---------------------------------------------------------------
  panelName: "Panel institucional",
  logout: "Cerrar sesión",
  loggingOut: "Cerrando sesión…",
  logoutFailed: "No pudimos cerrar la sesión.",

  // --- Login ---------------------------------------------------------------
  loginTagline: "El aire de tu institución, medido todos los días.",
  loginBlurb:
    "Accedé al estado de tu sensor, las recomendaciones del día y tus reportes.",
  loginTitle: "Ingresá a tu panel",
  loginSubtitle: "Usá el correo con el que registramos tu institución.",
  loginEmail: "Correo institucional",
  loginPassword: "Contraseña",
  loginSubmit: "Ingresar",
  loginSubmitting: "Ingresando…",
  loginHelp: "¿Problemas para entrar? Escribinos a",
  // Sits above `loginHelp`: the guide answers most of what would otherwise
  // become an email to the team, so it is offered before the contact address.
  loginGuide: "¿Primera vez acá? Leé la",
  loginGuideLink: "guía del panel",

  loginErrorCredentials:
    "Correo o contraseña incorrectos. Verificá los datos e intentá de nuevo.",
  loginErrorNoInstitution:
    "Esta cuenta no tiene acceso a un panel institucional.",
  loginErrorThrottled:
    "Demasiados intentos. Esperá unos minutos antes de volver a probar.",
  loginErrorUnexpected:
    "No pudimos completar el ingreso. Intentá de nuevo en unos segundos.",

  // --- Password recovery ---------------------------------------------------
  // Two screens: asking for the email, and choosing the new password from the
  // emailed link. The first one never says whether the address is registered —
  // the backend answers the same way either way, and the copy has to match.
  forgotLink: "¿Olvidaste tu contraseña?",
  forgotTagline: "Recuperá el acceso a tu panel.",
  forgotBlurb:
    "Te mandamos un enlace por correo para que elijas una contraseña nueva.",
  forgotTitle: "Recuperar contraseña",
  forgotSubtitle:
    "Escribí el correo de tu cuenta y te enviamos un enlace para restablecerla.",
  forgotEmail: "Correo de la cuenta",
  forgotSubmit: "Enviar enlace",
  forgotSubmitting: "Enviando…",
  forgotSentTitle: "Revisá tu correo",
  forgotSentBody:
    "Si ese correo tiene una cuenta en Respira, en unos minutos vas a recibir un enlace para elegir una contraseña nueva. Mirá también la carpeta de spam.",
  forgotSentHint: "El enlace vence en 24 horas y se puede usar una sola vez.",
  forgotBackToLogin: "Volver al ingreso",
  forgotErrorThrottled:
    "Pediste el enlace demasiadas veces. Esperá un rato antes de volver a intentar.",
  forgotErrorUnexpected:
    "No pudimos enviar el correo. Intentá de nuevo en unos segundos.",

  resetTagline: "Elegí tu nueva contraseña.",
  resetBlurb: "Después de guardarla vas a poder ingresar con ella al panel.",
  resetTitle: "Nueva contraseña",
  resetSubtitle: "Elegí una contraseña nueva para tu cuenta.",
  resetPassword: "Nueva contraseña",
  resetPasswordConfirm: "Repetí la contraseña",
  resetRules:
    "Al menos 10 caracteres, con una letra, un número y un carácter especial.",
  resetSubmit: "Guardar contraseña",
  resetSubmitting: "Guardando…",
  resetMismatch: "Las dos contraseñas no coinciden.",
  // Keyed by the `new_password_codes` the backend returns alongside Django's
  // own (English) validator messages.
  resetRuleTooShort: "La contraseña es demasiado corta.",
  resetRuleTooCommon: "Esa contraseña es demasiado común. Elegí otra.",
  resetRuleAllNumbers: "La contraseña no puede ser solo números.",
  resetRuleTooSimilar:
    "La contraseña se parece demasiado a tu correo o a tu nombre.",
  resetRuleNotComplex:
    "Falta mezclar caracteres: necesitás una letra, un número y un carácter especial.",
  resetRuleGeneric: "Esa contraseña no cumple los requisitos.",
  resetDoneTitle: "Listo, ya tenés contraseña nueva",
  resetDoneBody: "Ingresá al panel con tu correo y la contraseña que elegiste.",
  resetGoToLogin: "Ir al ingreso",
  resetInvalidTitle: "Este enlace ya no sirve",
  resetInvalidBody:
    "Puede haber vencido o haberse usado. Pedí uno nuevo y volvé a intentar.",
  resetRequestAnother: "Pedir un enlace nuevo",
  resetErrorThrottled:
    "Demasiados intentos. Esperá un rato antes de volver a probar.",
  resetErrorUnexpected:
    "No pudimos guardar la contraseña. Intentá de nuevo en unos segundos.",

  // --- Page ----------------------------------------------------------------
  pageTitle: "Estado de tu sensor",
  updatedAt: "Actualizado",

  // --- Sensor --------------------------------------------------------------
  sensorTitle: "Tu sensor",
  sensorOnline: "En línea",
  sensorOffline: "Fuera de línea",
  sensorLocation: "Ubicación",
  sensorCity: "Ciudad",
  sensorCoordinates: "Coordenadas",
  sensorLastReading: "Última medición",
  sensorContract: "Contrato",
  sensorNoReading: "Sin mediciones",
  sensorOfflineHint:
    "El sensor no envía datos nuevos. Ya estamos revisando el equipo.",
  contractActiveUntil: "Activo hasta",
  contractNoEnd: "Activo, sin fecha de término",

  // --- Air quality ---------------------------------------------------------
  airQualityTitle: "Calidad del aire",
  aqiUnit: "AQI PM2.5",
  recommendationsTitle: "Recomendaciones para hoy",
  airQualityEmptyTitle: "Tu sensor aún no reportó mediciones",
  airQualityEmptyBody:
    "En cuanto envíe la primera lectura, vas a ver acá el AQI y la recomendación del día.",

  // --- History -------------------------------------------------------------
  historyTitle: "Historial de calidad del aire · últimos 3 meses",
  historySubtitle: "Promedio diario",
  historyEmptyTitle: "Todavía no hay historial",
  historyEmptyBody:
    "El gráfico se arma con los promedios diarios de tu sensor. Aparece en cuanto haya al menos dos días de mediciones.",
  historyLegendSeries: "AQI diario",
  historyLegendThreshold: "Umbral de alerta",
  // Screen-reader summary of the chart. `{days}`, `{min}` and `{max}` are
  // filled in at render time.
  historyChartLabel:
    "{days} días con mediciones, entre {min} y {max} de AQI diario.",

  // --- Alerts --------------------------------------------------------------
  // "Configuración de alertas", not "Alertas": this card is the standing
  // configuration — the threshold in force and who it is watched for — while
  // the notifications section below is the history of what was actually sent.
  // Naming both "alertas" left two sections that sounded like the same thing.
  alertsTitle: "Configuración de alertas",
  alertsOn: "Activas",
  alertsOff: "Desactivadas",
  alertsThresholdSuffix: "AQI o más",
  alertsThresholdHelp: "Te avisamos cuando el sensor supere este valor.",
  alertsNoThreshold: "Sin umbral configurado.",
  alertsDisabledBody:
    "Tu institución no tiene alertas activas. Escribinos si querés activarlas.",
  alertsGroupsTitle: "Grupos sensibles",
  alertsNoGroups: "Todavía no hay grupos sensibles configurados.",
  alertsRequestChanges: "Solicitar cambios",
  // Subject line of the mail the "request changes" link opens.
  alertsRequestSubject: "Cambios en la configuración de alertas",

  // --- Action log ----------------------------------------------------------
  actionsTitle: "Acciones registradas",
  actionsEmptyTitle: "Todavía no registraste ninguna acción",
  actionsEmptyBody:
    "Anotá lo que hace tu institución cuando el aire empeora: queda como historial de lo que fueron respondiendo.",
  actionsLoadMore: "Ver más acciones",
  actionsLoadingMore: "Cargando…",
  actionsRespondsToAlert: "En respuesta a la alerta del",
  actionsRespondsToAlertPlain: "En respuesta a una alerta",
  actionsUnavailableTitle: "El registro de acciones todavía no está disponible",
  actionsUnavailableBody:
    "Se habilita en cuanto se publique la próxima versión de la plataforma.",

  actionFormTitle: "Registrar una acción",
  actionFormSensor: "Sensor",
  actionFormAlertLabel: "¿Responde a una alerta?",
  actionFormAlertOptional: "Opcional",
  actionFormAlertNone: "Ninguna — por iniciativa propia",
  actionFormNoteLabel: "¿Qué hicieron?",
  actionFormNotePlaceholder:
    "Ej.: Se suspendió el recreo al aire libre y se avisó a las familias.",
  actionFormNoteHelp: "La fecha y la hora se guardan solas al registrar.",
  actionFormSubmit: "Guardar acción",
  actionFormSubmitting: "Guardando…",
  actionFormSaved: "Acción guardada.",
  actionFormNoteRequired: "Contá brevemente qué hicieron antes de guardar.",
  actionFormNoteTooLong: "La nota es demasiado larga. Resumila un poco.",
  actionFormError: "No pudimos guardar la acción. Intentá de nuevo.",
  actionFormNoStation:
    "Necesitás un sensor asignado para registrar acciones. Escribinos si creés que es un error.",

  // --- Sensor notifications ------------------------------------------------
  notificationsTitle: "Notificaciones del sensor",
  notificationsEmptyTitle: "Todavía no hay notificaciones",
  notificationsEmptyBody:
    "Acá vas a ver los avisos que enviamos sobre tu sensor: las alertas por calidad del aire y los mensajes que te mandemos.",
  notificationsLoadMore: "Ver más notificaciones",
  notificationsLoadingMore: "Cargando…",
  notificationsUnavailableTitle:
    "Las notificaciones todavía no están disponibles",
  notificationsUnavailableBody:
    "Se habilitan en cuanto se publique la próxima versión de la plataforma.",
  // The two kinds of notification, as the badge on each row reads.
  notificationTypeAqi: "Calidad del aire",
  notificationTypeGeneral: "General",
  notificationThreshold: "Umbral",
  // The standing rule, stated above the history it produced — reads as one
  // sentence: "Te avisamos cuando el aire supere 100 AQI".
  notificationsRuleLead: "Te avisamos cuando el aire supere",
  notificationsRuleUnit: "AQI",
  notificationsRuleGroups: "Pensado para:",

  // --- Downloads -----------------------------------------------------------
  downloadsTitle: "Descargas",
  // Doubles as the month field's label and as the button when no month is
  // chosen yet, so it names the thing rather than the action.
  downloadMonthly: "Reporte mensual (PDF)",
  downloadMonthlyNote: "Resumen del último mes cerrado.",
  downloadRaw: "Historial crudo (CSV)",
  downloadRawNote: "Todas las mediciones desde el inicio del contrato.",
  downloadPreparing: "Generando…",
  downloadUnavailable: "Esta descarga todavía no está disponible.",
  downloadError: "No pudimos generar el archivo. Intentá de nuevo.",
  downloadPartial:
    "Descargamos el archivo, pero faltan algunos períodos que el sensor no pudo entregar.",

  // `{month}` is filled in by the card; see `formatMonthNote`.
  reportDownloadPdf: "Descargar PDF",
  reportMonthsLoading: "Cargando meses disponibles…",
  reportNoMonths: "Todavía no hay meses con mediciones.",
  reportMonthsError:
    "No pudimos cargar los meses disponibles. Se descargará el último mes cerrado.",

  // --- Contact -------------------------------------------------------------
  contactTitle: "Tu contacto en Respira",
  contactEmail: "Correo",
  contactHint:
    "Escribinos si el sensor aparece fuera de línea más de 24 horas.",

  // --- Shared states -------------------------------------------------------
  errorTitle: "No pudimos cargar estos datos",
  errorBody: "Revisá tu conexión y volvé a intentar. Si sigue igual, avisanos.",
  retry: "Reintentar",
  loading: "Cargando…",
  sessionExpiredTitle: "Tu sesión expiró",
  sessionExpiredBody: "Volvé a ingresar para seguir viendo tu panel.",
  goToLogin: "Ir al ingreso",
  noSensorTitle: "Tu institución todavía no tiene sensor asignado",
  noSensorBody:
    "Cuando el equipo esté instalado, este panel se activa solo. Escribinos si tenés dudas sobre la instalación.",
} as const;

export type InstitutionCopyKey = keyof typeof es;

// `en` and `pt` are typed against `es`, so a key added there and forgotten here
// is a build error rather than a string that silently falls back at runtime.
type Translation = Record<InstitutionCopyKey, string>;

const en: Translation = {
  // --- Shell ---------------------------------------------------------------
  panelName: "Institutional panel",
  logout: "Log out",
  loggingOut: "Logging out…",
  logoutFailed: "We couldn't log you out.",

  // --- Login ---------------------------------------------------------------
  loginTagline: "Your institution's air, measured every day.",
  loginBlurb:
    "Check your sensor's status, today's recommendations and your reports.",
  loginTitle: "Sign in to your panel",
  loginSubtitle: "Use the email address we registered your institution with.",
  loginEmail: "Institutional email",
  loginPassword: "Password",
  loginSubmit: "Sign in",
  loginSubmitting: "Signing in…",
  loginHelp: "Trouble signing in? Write to us at",
  loginGuide: "First time here? Read the",
  loginGuideLink: "panel guide",

  loginErrorCredentials:
    "Incorrect email or password. Check your details and try again.",
  loginErrorNoInstitution:
    "This account doesn't have access to an institutional panel.",
  loginErrorThrottled:
    "Too many attempts. Wait a few minutes before trying again.",
  loginErrorUnexpected:
    "We couldn't complete the sign-in. Try again in a few seconds.",

  // --- Password recovery ---------------------------------------------------
  forgotLink: "Forgot your password?",
  forgotTagline: "Get back into your panel.",
  forgotBlurb: "We'll email you a link to choose a new password.",
  forgotTitle: "Reset password",
  forgotSubtitle:
    "Enter your account's email and we'll send you a link to reset it.",
  forgotEmail: "Account email",
  forgotSubmit: "Send link",
  forgotSubmitting: "Sending…",
  forgotSentTitle: "Check your email",
  forgotSentBody:
    "If that address has a Respira account, you'll get a link to choose a new password within a few minutes. Check your spam folder too.",
  forgotSentHint: "The link expires in 24 hours and can only be used once.",
  forgotBackToLogin: "Back to sign in",
  forgotErrorThrottled:
    "You've requested the link too many times. Wait a while before trying again.",
  forgotErrorUnexpected:
    "We couldn't send the email. Try again in a few seconds.",

  resetTagline: "Choose your new password.",
  resetBlurb: "Once you save it, you can use it to sign in to the panel.",
  resetTitle: "New password",
  resetSubtitle: "Choose a new password for your account.",
  resetPassword: "New password",
  resetPasswordConfirm: "Repeat the password",
  resetRules:
    "At least 10 characters, with a letter, a number and a special character.",
  resetSubmit: "Save password",
  resetSubmitting: "Saving…",
  resetMismatch: "The two passwords don't match.",
  resetRuleTooShort: "The password is too short.",
  resetRuleTooCommon: "That password is too common. Choose another one.",
  resetRuleAllNumbers: "The password can't be only numbers.",
  resetRuleTooSimilar:
    "The password is too similar to your email or your name.",
  resetRuleNotComplex:
    "Mix in more characters: you need a letter, a number and a special character.",
  resetRuleGeneric: "That password doesn't meet the requirements.",
  resetDoneTitle: "Done, your password is set",
  resetDoneBody: "Sign in to the panel with your email and your new password.",
  resetGoToLogin: "Go to sign in",
  resetInvalidTitle: "This link no longer works",
  resetInvalidBody:
    "It may have expired or already been used. Request a new one and try again.",
  resetRequestAnother: "Request a new link",
  resetErrorThrottled: "Too many attempts. Wait a while before trying again.",
  resetErrorUnexpected:
    "We couldn't save the password. Try again in a few seconds.",

  // --- Page ----------------------------------------------------------------
  pageTitle: "Your sensor's status",
  updatedAt: "Updated",

  // --- Sensor --------------------------------------------------------------
  sensorTitle: "Your sensor",
  sensorOnline: "Online",
  sensorOffline: "Offline",
  sensorLocation: "Location",
  sensorCity: "City",
  sensorCoordinates: "Coordinates",
  sensorLastReading: "Last reading",
  sensorContract: "Contract",
  sensorNoReading: "No readings",
  sensorOfflineHint:
    "The sensor isn't sending new data. We're already looking into it.",
  contractActiveUntil: "Active until",
  contractNoEnd: "Active, with no end date",

  // --- Air quality ---------------------------------------------------------
  airQualityTitle: "Air quality",
  aqiUnit: "AQI PM2.5",
  recommendationsTitle: "Recommendations for today",
  airQualityEmptyTitle: "Your sensor hasn't reported any readings yet",
  airQualityEmptyBody:
    "As soon as it sends its first reading, you'll see the AQI and today's recommendation here.",

  // --- History -------------------------------------------------------------
  historyTitle: "Air quality history · last 3 months",
  historySubtitle: "Daily average",
  historyEmptyTitle: "No history yet",
  historyEmptyBody:
    "The chart is built from your sensor's daily averages. It appears once there are at least two days of readings.",
  historyLegendSeries: "Daily AQI",
  historyLegendThreshold: "Alert threshold",
  historyChartLabel:
    "{days} days with readings, between {min} and {max} daily AQI.",

  // --- Alerts --------------------------------------------------------------
  alertsTitle: "Alert settings",
  alertsOn: "On",
  alertsOff: "Off",
  alertsThresholdSuffix: "AQI or above",
  alertsThresholdHelp: "We'll let you know when the sensor goes above this.",
  alertsNoThreshold: "No threshold configured.",
  alertsDisabledBody:
    "Your institution doesn't have alerts turned on. Write to us if you'd like to enable them.",
  alertsGroupsTitle: "Sensitive groups",
  alertsNoGroups: "No sensitive groups configured yet.",
  alertsRequestChanges: "Request changes",
  alertsRequestSubject: "Changes to the alert settings",

  // --- Action log ----------------------------------------------------------
  actionsTitle: "Logged actions",
  actionsEmptyTitle: "You haven't logged any actions yet",
  actionsEmptyBody:
    "Note down what your institution does when the air gets worse: it becomes a record of how you responded.",
  actionsLoadMore: "See more actions",
  actionsLoadingMore: "Loading…",
  actionsRespondsToAlert: "In response to the alert of",
  actionsRespondsToAlertPlain: "In response to an alert",
  actionsUnavailableTitle: "The action log isn't available yet",
  actionsUnavailableBody:
    "It will be enabled as soon as the next version of the platform ships.",

  actionFormTitle: "Log an action",
  actionFormSensor: "Sensor",
  actionFormAlertLabel: "Is it in response to an alert?",
  actionFormAlertOptional: "Optional",
  actionFormAlertNone: "None — on our own initiative",
  actionFormNoteLabel: "What did you do?",
  actionFormNotePlaceholder:
    "E.g.: Outdoor recess was cancelled and families were notified.",
  actionFormNoteHelp:
    "The date and time are saved automatically when you log it.",
  actionFormSubmit: "Save action",
  actionFormSubmitting: "Saving…",
  actionFormSaved: "Action saved.",
  actionFormNoteRequired: "Briefly describe what you did before saving.",
  actionFormNoteTooLong: "The note is too long. Shorten it a little.",
  actionFormError: "We couldn't save the action. Try again.",
  actionFormNoStation:
    "You need an assigned sensor to log actions. Write to us if you think this is a mistake.",

  // --- Sensor notifications ------------------------------------------------
  notificationsTitle: "Sensor notifications",
  notificationsEmptyTitle: "No notifications yet",
  notificationsEmptyBody:
    "This is where you'll see the alerts we send about your sensor: air quality warnings and any messages we send you.",
  notificationsLoadMore: "See more notifications",
  notificationsLoadingMore: "Loading…",
  notificationsUnavailableTitle: "Notifications aren't available yet",
  notificationsUnavailableBody:
    "They're enabled as soon as the next version of the platform ships.",
  notificationTypeAqi: "Air quality",
  notificationTypeGeneral: "General",
  notificationThreshold: "Threshold",
  notificationsRuleLead: "We'll let you know when the air goes above",
  notificationsRuleUnit: "AQI",
  notificationsRuleGroups: "Watched for:",

  // --- Downloads -----------------------------------------------------------
  downloadsTitle: "Downloads",
  downloadMonthly: "Monthly report (PDF)",
  downloadMonthlyNote: "Summary of the last completed month.",
  downloadRaw: "Raw history (CSV)",
  downloadRawNote: "Every reading since the contract started.",
  downloadPreparing: "Generating…",
  downloadUnavailable: "This download isn't available yet.",
  downloadError: "We couldn't generate the file. Try again.",
  downloadPartial:
    "The file downloaded, but some periods are missing because the sensor could not provide them.",

  reportDownloadPdf: "Download PDF",
  reportMonthsLoading: "Loading available months…",
  reportNoMonths: "No months with measurements yet.",
  reportMonthsError:
    "We couldn't load the available months. The last complete month will be downloaded.",

  // --- Contact -------------------------------------------------------------
  contactTitle: "Your contact at Respira",
  contactEmail: "Email",
  contactHint:
    "Write to us if the sensor shows as offline for more than 24 hours.",

  // --- Shared states -------------------------------------------------------
  errorTitle: "We couldn't load this data",
  errorBody:
    "Check your connection and try again. If it keeps happening, let us know.",
  retry: "Try again",
  loading: "Loading…",
  sessionExpiredTitle: "Your session expired",
  sessionExpiredBody: "Sign in again to keep viewing your panel.",
  goToLogin: "Go to sign in",
  noSensorTitle: "Your institution doesn't have a sensor assigned yet",
  noSensorBody:
    "Once the equipment is installed, this panel activates on its own. Write to us if you have questions about the installation.",
};

const pt: Translation = {
  // --- Shell ---------------------------------------------------------------
  panelName: "Painel institucional",
  logout: "Sair",
  loggingOut: "Saindo…",
  logoutFailed: "Não conseguimos encerrar a sessão.",

  // --- Login ---------------------------------------------------------------
  loginTagline: "O ar da sua instituição, medido todos os dias.",
  loginBlurb:
    "Acesse o estado do seu sensor, as recomendações do dia e seus relatórios.",
  loginTitle: "Entre no seu painel",
  loginSubtitle: "Use o e-mail com o qual registramos sua instituição.",
  loginEmail: "E-mail institucional",
  loginPassword: "Senha",
  loginSubmit: "Entrar",
  loginSubmitting: "Entrando…",
  loginHelp: "Problemas para entrar? Escreva para",
  loginGuide: "Primeira vez aqui? Leia o",
  loginGuideLink: "guia do painel",

  loginErrorCredentials:
    "E-mail ou senha incorretos. Confira os dados e tente de novo.",
  loginErrorNoInstitution:
    "Esta conta não tem acesso a um painel institucional.",
  loginErrorThrottled:
    "Tentativas demais. Espere alguns minutos antes de tentar de novo.",
  loginErrorUnexpected:
    "Não conseguimos concluir a entrada. Tente de novo em alguns segundos.",

  // --- Password recovery ---------------------------------------------------
  forgotLink: "Esqueceu sua senha?",
  forgotTagline: "Recupere o acesso ao seu painel.",
  forgotBlurb: "Enviamos um link por e-mail para você escolher uma senha nova.",
  forgotTitle: "Recuperar senha",
  forgotSubtitle:
    "Escreva o e-mail da sua conta e enviamos um link para redefini-la.",
  forgotEmail: "E-mail da conta",
  forgotSubmit: "Enviar link",
  forgotSubmitting: "Enviando…",
  forgotSentTitle: "Confira seu e-mail",
  forgotSentBody:
    "Se esse e-mail tiver uma conta na Respira, em alguns minutos você vai receber um link para escolher uma senha nova. Veja também a pasta de spam.",
  forgotSentHint: "O link vence em 24 horas e pode ser usado uma única vez.",
  forgotBackToLogin: "Voltar para a entrada",
  forgotErrorThrottled:
    "Você pediu o link vezes demais. Espere um pouco antes de tentar de novo.",
  forgotErrorUnexpected:
    "Não conseguimos enviar o e-mail. Tente de novo em alguns segundos.",

  resetTagline: "Escolha sua nova senha.",
  resetBlurb: "Depois de salvá-la, você poderá entrar no painel com ela.",
  resetTitle: "Nova senha",
  resetSubtitle: "Escolha uma senha nova para sua conta.",
  resetPassword: "Nova senha",
  resetPasswordConfirm: "Repita a senha",
  resetRules:
    "Pelo menos 10 caracteres, com uma letra, um número e um caractere especial.",
  resetSubmit: "Salvar senha",
  resetSubmitting: "Salvando…",
  resetMismatch: "As duas senhas não coincidem.",
  resetRuleTooShort: "A senha é curta demais.",
  resetRuleTooCommon: "Essa senha é comum demais. Escolha outra.",
  resetRuleAllNumbers: "A senha não pode ser só números.",
  resetRuleTooSimilar: "A senha é parecida demais com seu e-mail ou seu nome.",
  resetRuleNotComplex:
    "Falta misturar caracteres: você precisa de uma letra, um número e um caractere especial.",
  resetRuleGeneric: "Essa senha não cumpre os requisitos.",
  resetDoneTitle: "Pronto, sua senha nova está salva",
  resetDoneBody: "Entre no painel com seu e-mail e a senha que você escolheu.",
  resetGoToLogin: "Ir para a entrada",
  resetInvalidTitle: "Este link não vale mais",
  resetInvalidBody:
    "Pode ter vencido ou já ter sido usado. Peça um novo e tente de novo.",
  resetRequestAnother: "Pedir um link novo",
  resetErrorThrottled:
    "Tentativas demais. Espere um pouco antes de tentar de novo.",
  resetErrorUnexpected:
    "Não conseguimos salvar a senha. Tente de novo em alguns segundos.",

  // --- Page ----------------------------------------------------------------
  pageTitle: "Estado do seu sensor",
  updatedAt: "Atualizado",

  // --- Sensor --------------------------------------------------------------
  sensorTitle: "Seu sensor",
  sensorOnline: "On-line",
  sensorOffline: "Fora do ar",
  sensorLocation: "Localização",
  sensorCity: "Cidade",
  sensorCoordinates: "Coordenadas",
  sensorLastReading: "Última medição",
  sensorContract: "Contrato",
  sensorNoReading: "Sem medições",
  sensorOfflineHint:
    "O sensor não está enviando dados novos. Já estamos verificando o equipamento.",
  contractActiveUntil: "Ativo até",
  contractNoEnd: "Ativo, sem data de término",

  // --- Air quality ---------------------------------------------------------
  airQualityTitle: "Qualidade do ar",
  aqiUnit: "AQI PM2.5",
  recommendationsTitle: "Recomendações para hoje",
  airQualityEmptyTitle: "Seu sensor ainda não reportou medições",
  airQualityEmptyBody:
    "Assim que enviar a primeira leitura, você vai ver aqui o AQI e a recomendação do dia.",

  // --- History -------------------------------------------------------------
  historyTitle: "Histórico de qualidade do ar · últimos 3 meses",
  historySubtitle: "Média diária",
  historyEmptyTitle: "Ainda não há histórico",
  historyEmptyBody:
    "O gráfico é montado com as médias diárias do seu sensor. Aparece assim que houver pelo menos dois dias de medições.",
  historyLegendSeries: "AQI diário",
  historyLegendThreshold: "Limite de alerta",
  historyChartLabel:
    "{days} dias com medições, entre {min} e {max} de AQI diário.",

  // --- Alerts --------------------------------------------------------------
  alertsTitle: "Configuração de alertas",
  alertsOn: "Ativos",
  alertsOff: "Desativados",
  alertsThresholdSuffix: "AQI ou mais",
  alertsThresholdHelp: "Avisamos você quando o sensor passar deste valor.",
  alertsNoThreshold: "Sem limite configurado.",
  alertsDisabledBody:
    "Sua instituição não tem alertas ativos. Escreva para nós se quiser ativá-los.",
  alertsGroupsTitle: "Grupos sensíveis",
  alertsNoGroups: "Ainda não há grupos sensíveis configurados.",
  alertsRequestChanges: "Solicitar mudanças",
  alertsRequestSubject: "Mudanças na configuração de alertas",

  // --- Action log ----------------------------------------------------------
  actionsTitle: "Ações registradas",
  actionsEmptyTitle: "Você ainda não registrou nenhuma ação",
  actionsEmptyBody:
    "Anote o que sua instituição faz quando o ar piora: fica como histórico do que vocês foram respondendo.",
  actionsLoadMore: "Ver mais ações",
  actionsLoadingMore: "Carregando…",
  actionsRespondsToAlert: "Em resposta ao alerta de",
  actionsRespondsToAlertPlain: "Em resposta a um alerta",
  actionsUnavailableTitle: "O registro de ações ainda não está disponível",
  actionsUnavailableBody:
    "Será habilitado assim que a próxima versão da plataforma for publicada.",

  actionFormTitle: "Registrar uma ação",
  actionFormSensor: "Sensor",
  actionFormAlertLabel: "Responde a um alerta?",
  actionFormAlertOptional: "Opcional",
  actionFormAlertNone: "Nenhum — por iniciativa própria",
  actionFormNoteLabel: "O que vocês fizeram?",
  actionFormNotePlaceholder:
    "Ex.: O recreio ao ar livre foi suspenso e as famílias foram avisadas.",
  actionFormNoteHelp: "A data e a hora são salvas sozinhas ao registrar.",
  actionFormSubmit: "Salvar ação",
  actionFormSubmitting: "Salvando…",
  actionFormSaved: "Ação salva.",
  actionFormNoteRequired:
    "Conte brevemente o que vocês fizeram antes de salvar.",
  actionFormNoteTooLong: "A nota está longa demais. Resuma um pouco.",
  actionFormError: "Não conseguimos salvar a ação. Tente de novo.",
  actionFormNoStation:
    "Você precisa de um sensor atribuído para registrar ações. Escreva para nós se achar que é um erro.",

  // --- Sensor notifications ------------------------------------------------
  notificationsTitle: "Notificações do sensor",
  notificationsEmptyTitle: "Ainda não há notificações",
  notificationsEmptyBody:
    "Aqui você verá os avisos que enviamos sobre o seu sensor: os alertas de qualidade do ar e as mensagens que mandarmos.",
  notificationsLoadMore: "Ver mais notificações",
  notificationsLoadingMore: "Carregando…",
  notificationsUnavailableTitle: "As notificações ainda não estão disponíveis",
  notificationsUnavailableBody:
    "Elas são habilitadas assim que a próxima versão da plataforma for publicada.",
  notificationTypeAqi: "Qualidade do ar",
  notificationTypeGeneral: "Geral",
  notificationThreshold: "Limite",
  notificationsRuleLead: "Avisamos você quando o ar passar de",
  notificationsRuleUnit: "AQI",
  notificationsRuleGroups: "Pensado para:",

  // --- Downloads -----------------------------------------------------------
  downloadsTitle: "Downloads",
  downloadMonthly: "Relatório mensal (PDF)",
  downloadMonthlyNote: "Resumo do último mês fechado.",
  downloadRaw: "Histórico bruto (CSV)",
  downloadRawNote: "Todas as medições desde o início do contrato.",
  downloadPreparing: "Gerando…",
  downloadUnavailable: "Este download ainda não está disponível.",
  downloadError: "Não conseguimos gerar o arquivo. Tente de novo.",
  downloadPartial:
    "Baixamos o arquivo, mas faltam alguns períodos que o sensor não conseguiu entregar.",

  reportDownloadPdf: "Baixar PDF",
  reportMonthsLoading: "Carregando meses disponíveis…",
  reportNoMonths: "Ainda não há meses com medições.",
  reportMonthsError:
    "Não conseguimos carregar os meses disponíveis. Será baixado o último mês fechado.",

  // --- Contact -------------------------------------------------------------
  contactTitle: "Seu contato na Respira",
  contactEmail: "E-mail",
  contactHint:
    "Escreva para nós se o sensor aparecer fora do ar por mais de 24 horas.",

  // --- Shared states -------------------------------------------------------
  errorTitle: "Não conseguimos carregar estes dados",
  errorBody:
    "Confira sua conexão e tente de novo. Se continuar igual, avise a gente.",
  retry: "Tentar de novo",
  loading: "Carregando…",
  sessionExpiredTitle: "Sua sessão expirou",
  sessionExpiredBody: "Entre de novo para continuar vendo seu painel.",
  goToLogin: "Ir para a entrada",
  noSensorTitle: "Sua instituição ainda não tem sensor atribuído",
  noSensorBody:
    "Quando o equipamento estiver instalado, este painel se ativa sozinho. Escreva para nós se tiver dúvidas sobre a instalação.",
};

export const institution = { es, en, pt } as const;

/**
 * Returns the institutional copy for `lang`, falling back to Spanish for any
 * key a translation is missing — the same contract as `useTranslations` for the
 * public dictionary, so a partial translation degrades instead of breaking.
 *
 * Returns an object rather than a `t(key)` function because these components
 * read many keys each and `copy.x` keeps their JSX unchanged.
 */
export function useInstitutionCopy(lang: Lang): Translation {
  const dictionary = institution[lang];
  if (!dictionary || dictionary === institution[DEFAULT_LANG]) {
    return institution[DEFAULT_LANG];
  }
  return { ...institution[DEFAULT_LANG], ...dictionary };
}

/** Fills `{name}` placeholders, for the few strings that carry values. */
export function format(
  template: string,
  values: Record<string, string | number>,
): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}

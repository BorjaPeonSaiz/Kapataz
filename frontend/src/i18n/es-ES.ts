// Textos de usuario en español de España (RNF-11). Claves por funcionalidad.
export default {
  app: {
    name: "Kapataz",
    skipToContent: "Saltar al contenido",
  },
  common: {
    loading: "Cargando…",
    optional: "opcional",
  },
  errors: {
    network: "No hay conexión. No se ha guardado nada. Inténtalo cuando vuelva.",
    server:
      "Algo ha ido mal por nuestra parte y no se ha guardado. Inténtalo de nuevo; si sigue igual, escríbenos.",
    // Mensajes por el `type` del error de la API (/problemas/...).
    problem: {
      badCredentials: "El correo o la contraseña no son correctos. Revísalos e inténtalo de nuevo.",
      registrationClosed:
        "El registro está cerrado hasta el lanzamiento. Todavía no se pueden crear cuentas nuevas.",
      subscriptionInactive:
        "Tu suscripción no está activa, así que el asistente está en pausa. Reactívala para volver a usarlo.",
      csrfInvalid: "No hemos podido comprobar tu sesión. Recarga la página e inténtalo de nuevo.",
      invalidData: "Hay datos que no son válidos. Revísalos e inténtalo de nuevo.",
      weakPassword:
        "La contraseña es demasiado débil. Usa una más larga y que no sea fácil de adivinar.",
      invalidEmail: "El correo electrónico no es válido. Revisa que lo has escrito bien.",
      invalidLink: "El enlace no es válido o ha caducado. Pide uno nuevo desde el registro.",
      notAuthenticated: "Tu sesión ha terminado. Entra de nuevo para continuar.",
      notFound: "No encontramos lo que buscas.",
      internal:
        "Algo ha ido mal por nuestra parte y no se ha guardado. Inténtalo de nuevo; si sigue igual, escríbenos.",
      unknown:
        "No se ha podido completar la acción. Inténtalo de nuevo; si sigue igual, escríbenos.",
    },
  },
  account: {
    fields: {
      email: "Correo electrónico",
      password: "Contraseña",
    },
    validation: {
      emailRequired: "Escribe tu correo electrónico.",
      passwordRequired: "Escribe tu contraseña.",
    },
    login: {
      title: "Entra en Kapataz",
      submit: "Entrar",
      submitting: "Entrando…",
      noAccount: "¿Todavía no tienes cuenta?",
      goRegister: "Crear una cuenta",
    },
    register: {
      title: "Crea tu cuenta",
      submit: "Crear cuenta",
      submitting: "Creando cuenta…",
      haveAccount: "¿Ya tienes cuenta?",
      goLogin: "Entrar",
      done: "Te hemos enviado un correo para confirmar tu dirección. Ábrelo y pulsa el enlace para terminar.",
    },
    verify: {
      title: "Confirmar tu correo",
      working: "Estamos confirmando tu correo…",
      success: "Correo confirmado. Ya puedes entrar.",
      failure:
        "No hemos podido confirmar tu correo. El enlace puede haber caducado: pide uno nuevo desde el registro.",
      missingToken: "Falta el enlace de confirmación. Abre el enlace que te llegó por correo.",
      goLogin: "Entrar",
    },
  },
  chat: {
    title: "Asistente",
    logout: "Cerrar sesión",
    logoutWorking: "Cerrando sesión…",
    log: "Conversación con el asistente",
    empty: "Escribe lo que necesitas. Por ejemplo: «¿Cuánto me debe Ana Gil?»",
    input: "Tu mensaje",
    placeholder: "Escribe tu mensaje…",
    send: "Enviar",
    sending: "Enviando…",
    you: "Tú",
    assistant: "Asistente",
    typing: "El asistente está escribiendo",
    responding: "El asistente está respondiendo",
    errorBubble: "No se ha podido terminar la respuesta. Puedes volver a enviar el mensaje.",
    unavailable:
      "El asistente no está disponible ahora mismo. Todo lo demás funciona con normalidad.",
    unavailableHint: "Asistente en pausa",
    offline: "No hay conexión. No se ha enviado nada. Inténtalo cuando vuelva.",
    retry: "Volver a intentarlo",
  },
};

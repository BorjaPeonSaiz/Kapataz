// Errores RFC 9457 (application/problem+json). El `type` fija el mensaje para la persona;
// lo desconocido cae en un mensaje genérico.
const BASE = "/problemas/";

export const PROBLEM = {
  badCredentials: `${BASE}credenciales-incorrectas`,
  registrationClosed: `${BASE}registro-cerrado`,
  subscriptionInactive: `${BASE}suscripcion-inactiva`,
  csrfInvalid: `${BASE}csrf-no-valido`,
  invalidData: `${BASE}datos-no-validos`,
  weakPassword: `${BASE}contrasena-debil`,
  invalidEmail: `${BASE}email-no-valido`,
  invalidLink: `${BASE}enlace-no-valido`,
  notAuthenticated: `${BASE}no-autenticado`,
  notFound: `${BASE}no-encontrado`,
  internal: `${BASE}error-interno`,
} as const;

// type → clave de i18n (errors.problem.*).
const MESSAGE_KEYS: Record<string, string> = {
  [PROBLEM.badCredentials]: "errors.problem.badCredentials",
  [PROBLEM.registrationClosed]: "errors.problem.registrationClosed",
  [PROBLEM.subscriptionInactive]: "errors.problem.subscriptionInactive",
  [PROBLEM.csrfInvalid]: "errors.problem.csrfInvalid",
  [PROBLEM.invalidData]: "errors.problem.invalidData",
  [PROBLEM.weakPassword]: "errors.problem.weakPassword",
  [PROBLEM.invalidEmail]: "errors.problem.invalidEmail",
  [PROBLEM.invalidLink]: "errors.problem.invalidLink",
  [PROBLEM.notAuthenticated]: "errors.problem.notAuthenticated",
  [PROBLEM.notFound]: "errors.problem.notFound",
  [PROBLEM.internal]: "errors.problem.internal",
};

export function problemType(error: unknown): string | undefined {
  if (typeof error === "object" && error !== null && "type" in error) {
    const type = (error as { type?: unknown }).type;
    return typeof type === "string" ? type : undefined;
  }
  return undefined;
}

/** Clave de i18n del mensaje para un error de la API; genérica si el type no se conoce. */
export function problemMessageKey(error: unknown): string {
  const type = problemType(error);
  return (type && MESSAGE_KEYS[type]) || "errors.problem.unknown";
}

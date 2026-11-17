import { createRouter, createWebHistory, type RouterHistory } from "vue-router";
import { useSessionStore } from "@/stores/session";

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const router = createRouter({
    history,
    routes: [
      {
        path: "/",
        name: "chat",
        component: () => import("@/features/chat/ChatView.vue"),
        meta: { requiresAuth: true },
      },
      {
        path: "/",
        component: () => import("@/features/account/AccessLayout.vue"),
        children: [
          {
            path: "acceso",
            name: "login",
            component: () => import("@/features/account/LoginView.vue"),
          },
          {
            path: "registro",
            name: "register",
            component: () => import("@/features/account/RegisterView.vue"),
          },
          {
            path: "verificar-email",
            name: "verify-email",
            component: () => import("@/features/account/VerifyEmailView.vue"),
          },
        ],
      },
      { path: "/:pathMatch(.*)*", redirect: { name: "chat" } },
    ],
  });

  // Sin sesión (GET /api/auth/me devuelve 401) → pantalla de acceso.
  router.beforeEach(async (to) => {
    const session = useSessionStore();
    if (!session.loaded) await session.fetchMe();
    if (to.meta.requiresAuth && !session.user) return { name: "login" };
    if ((to.name === "login" || to.name === "register") && session.user) return { name: "chat" };
    return true;
  });

  return router;
}

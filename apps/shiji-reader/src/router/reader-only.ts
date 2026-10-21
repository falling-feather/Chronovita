import { createRouter, createWebHistory } from "vue-router";

const ReaderPassage = () => import("../pages/ReaderPassage.vue");
const ReaderVolume = () => import("../pages/ReaderVolume.vue");

const firstVolume = { name: "reader-volume", params: { volumeNo: "1" } };

const readerRouter = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", redirect: firstVolume },
    { path: "/books/shiji", redirect: firstVolume },
    { path: "/reader/shiji/volume/:volumeNo", name: "reader-volume", component: ReaderVolume },
    { path: "/reader/:passageId", name: "reader-passage", component: ReaderPassage },
    { path: "/:pathMatch(.*)*", redirect: firstVolume },
  ],
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { left: 0, top: 0 };
  },
});

export default readerRouter;

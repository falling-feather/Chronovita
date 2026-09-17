import { createRouter, createWebHistory } from "vue-router";

import ReaderPassage from "../pages/ReaderPassage.vue";
import ReaderVolume from "../pages/ReaderVolume.vue";
import ReaderScanPage from "../pages/ReaderScanPage.vue";

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", redirect: "/reader/shiji/volume/1" },
    { path: "/index.html", redirect: "/reader/shiji/volume/1" },
    { path: "/reader/scan/:pageId", name: "reader-scan-page", component: ReaderScanPage },
    { path: "/reader/shiji/volume/:volumeNo", name: "reader-volume", component: ReaderVolume },
    { path: "/reader/:passageId", name: "reader-passage", component: ReaderPassage },
  ]
});

export default router;

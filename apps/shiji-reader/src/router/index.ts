import { createRouter, createWebHashHistory } from "vue-router";

import ReaderPassage from "../pages/ReaderPassage.vue";
import ReaderVolume from "../pages/ReaderVolume.vue";
import ReaderScanPage from "../pages/ReaderScanPage.vue";
import BookCatalog from "../pages/BookCatalog.vue";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", redirect: "/reader/shiji/volume/1" },
    { path: "/index.html", redirect: "/reader/shiji/volume/1" },
    { path: "/books/:bookId(shiji)", name: "shiji-catalog", component: BookCatalog },
    { path: "/reader/scan/:pageId", name: "reader-scan-page", component: ReaderScanPage },
    { path: "/reader/shiji/volume/:volumeNo", name: "reader-volume", component: ReaderVolume },
    { path: "/reader/:passageId", name: "reader-passage", component: ReaderPassage },
    { path: "/:pathMatch(.*)*", redirect: "/books/shiji" },
  ]
});

export default router;

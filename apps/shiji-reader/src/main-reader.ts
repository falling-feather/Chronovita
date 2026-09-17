import { createApp } from "vue";

import AppReader from "./AppReader.vue";
import readerRouter from "./router/reader-only";
import "./styles/base.css";

createApp(AppReader).use(readerRouter).mount("#app");

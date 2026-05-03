import { message as staticMessage } from 'antd';
import type { MessageInstance } from 'antd/es/message/interface';

let bound: MessageInstance | null = null;

export const bindMessage = (m: MessageInstance) => { bound = m; };

export const toast: MessageInstance = new Proxy({} as MessageInstance, {
  get(_t, prop) {
    const target = (bound ?? staticMessage) as unknown as Record<string, unknown>;
    return target[prop as string];
  },
});

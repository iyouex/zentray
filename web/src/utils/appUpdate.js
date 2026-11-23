/**
 * 应用里实际使用的更新状态镜像（绑定真实接口）。
 *
 * createUpdateStore 本身不依赖任何接口实现，所以在 node 里可以直接测
 * （web/tests/updateStore.test.mjs 注入假接口）。
 */
import * as api from '../api/client'
import { createUpdateStore } from './updateStore'

export const updateStore = createUpdateStore(api)

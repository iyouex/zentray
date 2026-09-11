/**
 * GSAP 动效基座（spec §2 单一事实源）。
 * 插件只在这里注册一次；曲线与 CSS 侧 --zt-ease-* 同参数。
 */
import { gsap } from 'gsap'
import { Flip } from 'gsap/Flip'
import { SplitText } from 'gsap/SplitText'
import { CustomEase } from 'gsap/CustomEase'

gsap.registerPlugin(Flip, SplitText, CustomEase)

let spring = 'back.out(1.6)'
let out = 'power2.out'
try {
  CustomEase.create('zt-spring', 'cubic-bezier(0.34,1.56,0.64,1)')
  CustomEase.create('zt-out', 'cubic-bezier(0.22,1,0.36,1)')
  spring = 'zt-spring'
  out = 'zt-out'
} catch (e) {
  /* ponytail: CustomEase 解析失败的内置曲线回退，手感近似 */
}

export { gsap, Flip, SplitText }

export const EASE = { spring, out }

/** 时长（秒）——spec §2；命名与 CSS 令牌一一对应 */
export const DUR = {
  leave: 0.12,
  enter: 0.26,
  theme: 0.45,
  shape: 0.35,
  flip: 0.4,
  staggerCards: 0.04,
  staggerModal: 0.03,
  staggerChars: 0.035,
  reduce: 0.14,
}

/** 动效=关：所有补间时长归零（调用方仍应尽早 return，此为兜底） */
export function motionOff() {
  return typeof document !== 'undefined' && document.body.classList.contains('zt-motion-off')
}

/** 系统减动效：降级为 140ms 纯淡入 */
export function isReduced() {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch (e) {
    return false
  }
}

/** 关档把时长压为零；正常档原样返回 */
export function dur(v) {
  return motionOff() ? 0.001 : v
}

/**
 * v-stagger：弹层/区块内容依次浮升（spec §3.3，原型场景 4）。
 * 挂在内容根节点上，其直接子块 stagger 入场；关档/减动效不动作。
 */
import { gsap, EASE, DUR, motionOff, isReduced } from '../motion'

export const vStagger = {
  mounted(el) {
    if (motionOff() || isReduced()) return
    const kids = el.querySelectorAll(':scope > *')
    if (!kids.length) return
    gsap.from(kids, {
      y: 14,
      autoAlpha: 0,
      duration: DUR.enter,
      stagger: DUR.staggerModal,
      ease: EASE.spring,
      clearProps: 'all',
      delay: 0.05,
    })
  },
}

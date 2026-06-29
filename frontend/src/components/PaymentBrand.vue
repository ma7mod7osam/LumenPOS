<template>
  <span class="pay-brand" :style="{ height: px }">
    <span v-if="logo" class="pay-logo" v-html="logo" />
    <Icon v-else :name="fallback" :size="size" />
  </span>
</template>

<script setup>
// Renders the card-scheme / wallet logo for a Mode of Payment (Visa,
// Mastercard, mada, Amex, Tamara, …) on a white chip so it stays legible in
// light and dark themes. Falls back to a generic line icon (cash/bank/card)
// for non-scheme methods. Marks are simplified, recognisable representations.
import { computed } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  brand: { type: String, default: '' },
  type: { type: String, default: '' },
  size: { type: [Number, String], default: 26 },
})

const px = computed(() => (typeof props.size === 'number' ? `${props.size}px` : props.size))
const fallback = computed(() =>
  props.type === 'Cash' ? 'cash' : props.type === 'Bank' ? 'bank' : 'card'
)

const FONT = "font-family='Arial, Helvetica, sans-serif'"
const LOGOS = {
  mastercard:
    "<svg viewBox='0 0 40 24'><circle cx='16' cy='12' r='9' fill='#EB001B'/>" +
    "<circle cx='24' cy='12' r='9' fill='#F79E1B'/>" +
    "<path d='M20 5.2a9 9 0 0 0 0 13.6 9 9 0 0 0 0-13.6z' fill='#FF5F00'/></svg>",
  visa:
    `<svg viewBox='0 0 60 20'><text x='30' y='15.5' text-anchor='middle' ${FONT} ` +
    "font-weight='700' font-style='italic' font-size='16' letter-spacing='1.5' fill='#1434CB'>VISA</text></svg>",
  amex:
    "<svg viewBox='0 0 44 28'><rect width='44' height='28' rx='3' fill='#006FCF'/>" +
    `<text x='22' y='18' text-anchor='middle' ${FONT} font-weight='800' font-size='10' ` +
    "letter-spacing='0.5' fill='#fff'>AMEX</text></svg>",
  mada:
    `<svg viewBox='0 0 60 22'><text x='30' y='17' text-anchor='middle' ${FONT} ` +
    "font-weight='800' font-size='17' fill='#0E2C5A'>mada</text></svg>",
  tamara:
    `<svg viewBox='0 0 84 20'><text x='42' y='15' text-anchor='middle' ${FONT} ` +
    "font-weight='700' font-size='15' fill='#7B2FF2'>tamara</text></svg>",
  tabby:
    `<svg viewBox='0 0 60 20'><text x='30' y='15' text-anchor='middle' ${FONT} ` +
    "font-weight='800' font-size='15' fill='#111111'>tabby</text></svg>",
  stcpay:
    `<svg viewBox='0 0 74 22'><text x='37' y='16' text-anchor='middle' ${FONT} ` +
    "font-weight='800' font-size='14' fill='#4F2D7F'>stc pay</text></svg>",
  applepay:
    "<svg viewBox='0 0 92 22'><path d='M11.5 7.2c.6-.7 1-1.7.9-2.7-.9 0-1.9.6-2.5 1.3-.5.6-1 1.6-.9 2.6 1 .1 1.9-.5 2.5-1.2z' fill='#111'/>" +
    "<path d='M12.4 8.6c-1.4-.1-2.5.8-3.2.8-.7 0-1.7-.7-2.7-.7-1.4 0-2.7.8-3.4 2-1.5 2.5-.4 6.2 1 8.3.7 1 1.5 2.1 2.6 2.1 1 0 1.4-.7 2.7-.7 1.2 0 1.6.7 2.7.6 1.1 0 1.8-1 2.5-2 .8-1.2 1.1-2.3 1.1-2.3s-2.1-.8-2.2-3.2c0-2 1.6-2.9 1.7-3-1-1.4-2.4-1.5-3-1.6z' fill='#111'/>" +
    `<text x='34' y='16' ${FONT} font-weight='600' font-size='14' fill='#111'>Pay</text></svg>`,
}

const logo = computed(() => LOGOS[props.brand] || '')
</script>

<style scoped>
.pay-brand { display: inline-flex; align-items: center; }
.pay-logo {
  height: 100%;
  display: inline-flex;
  align-items: center;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 5px;
  padding: 4px 7px;
  box-sizing: border-box;
}
.pay-logo :deep(svg) { height: 100%; width: auto; display: block; }
</style>

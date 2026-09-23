// The installed-app icons, drawn as pixels and encoded as PNG here so the repo
// needs no image toolchain. The mark is the LumenPOS bars on the brand square,
// the same shape as the favicon in pos.html.
import { deflateSync } from 'node:zlib'
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// Written into the Vite public folder, from where every build copies them
// into the shipped asset folder.
const OUT = fileURLToPath(new URL('../frontend/public/', import.meta.url))

// brand gradient ends, top-left to bottom-right
const C1 = [42, 123, 255]
const C2 = [11, 67, 184]

function draw(size) {
  const px = Buffer.alloc(size * size * 4)
  const radius = Math.round(size * 0.22)
  const set = (x, y, r, g, b, a) => {
    const i = (y * size + x) * 4
    px[i] = r
    px[i + 1] = g
    px[i + 2] = b
    px[i + 3] = a
  }
  const inRounded = (x, y) => {
    const near = (cx, cy) => (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2
    if (x >= radius && x < size - radius) return true
    if (y >= radius && y < size - radius) return true
    return (
      near(radius, radius) ||
      near(size - radius - 1, radius) ||
      near(radius, size - radius - 1) ||
      near(size - radius - 1, size - radius - 1)
    )
  }
  // the four bars, in the 100x100 space of the favicon, then scaled
  const bars = [
    [36, 36, 7.5, 38, 1],
    [48, 55, 4.5, 19, 0.62],
    [57, 55, 7.5, 19, 1],
    [69, 55, 4.5, 19, 1],
  ]
  const s = size / 100
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      if (!inRounded(x, y)) {
        set(x, y, 0, 0, 0, 0)
        continue
      }
      const t = (x / size + y / size) / 2
      let r = Math.round(C1[0] + (C2[0] - C1[0]) * t)
      let g = Math.round(C1[1] + (C2[1] - C1[1]) * t)
      let b = Math.round(C1[2] + (C2[2] - C1[2]) * t)
      for (const [bx, by, bw, bh, alpha] of bars) {
        if (x >= bx * s && x < (bx + bw) * s && y >= by * s && y < (by + bh) * s) {
          r = Math.round(r + (255 - r) * alpha)
          g = Math.round(g + (255 - g) * alpha)
          b = Math.round(b + (255 - b) * alpha)
        }
      }
      set(x, y, r, g, b, 255)
    }
  }
  return px
}

function png(size) {
  const px = draw(size)
  const raw = Buffer.alloc((size * 4 + 1) * size)
  for (let y = 0; y < size; y += 1) {
    raw[y * (size * 4 + 1)] = 0 // filter: none
    px.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4)
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4)
    len.writeUInt32BE(data.length)
    const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
    const crc = Buffer.alloc(4)
    crc.writeUInt32BE(crc32(body) >>> 0)
    return Buffer.concat([len, body, crc])
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

let table = null
function crc32(buf) {
  if (!table) {
    table = new Int32Array(256)
    for (let n = 0; n < 256; n += 1) {
      let c = n
      for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
      table[n] = c
    }
  }
  let c = -1
  for (const byte of buf) c = table[(c ^ byte) & 0xff] ^ (c >>> 8)
  return c ^ -1
}

for (const size of [192, 512]) {
  const file = OUT + `icon-${size}.png`
  writeFileSync(file, png(size))
  console.log('wrote', file)
}

import { useMemo } from 'react'
import bonfire from '../assets/bonfire.png'

// Ícono de la hoguera (reemplaza a la llama en toda la app).
export function Bonfire({ size = 32 }) {
  return <img src={bonfire} alt="" aria-hidden="true" width={size} height={size} className="bonfire" />
}

// Ascuas que suben desde la hoguera del fondo.
export function Embers({ count = 32 }) {
  const embers = useMemo(
    () =>
      Array.from({ length: count }, () => {
        const size = 1 + Math.random() * 2.6
        return {
          width: size,
          height: size,
          left: `${40 + Math.random() * 60}%`,
          '--dx': `${-40 - Math.random() * 160}px`,
          animationDuration: `${8 + Math.random() * 12}s`,
          animationDelay: `${-Math.random() * 20}s`,
        }
      }),
    [count],
  )
  return (
    <div className="embers" aria-hidden="true">
      {embers.map((style, i) => (
        <i key={i} style={style} />
      ))}
    </div>
  )
}

// Frase icónica entre dos líneas doradas.
export function Quote({ children }) {
  return (
    <div className="rule">
      <span className="quote">{children}</span>
    </div>
  )
}

// Personaje decorativo: nunca recibe clics ni lo leen los lectores de pantalla.
export function Character({ src, className = '', style }) {
  return <img src={src} alt="" aria-hidden="true" className={`char ${className}`} style={style} />
}

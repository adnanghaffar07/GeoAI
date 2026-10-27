import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from '@/app'
import './index.css'

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Missing <div id="root"> in index.html')
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

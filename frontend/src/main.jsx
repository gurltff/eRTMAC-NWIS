import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import { LiveProvider } from './context/LiveContext'
import { ThemeProvider } from './context/ThemeContext'
import './styles/theme.css'
import './styles/layout.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider>
      <AuthProvider>
        <LiveProvider>
          <HashRouter>
            <App />
          </HashRouter>
        </LiveProvider>
      </AuthProvider>
    </ThemeProvider>
  </React.StrictMode>,
)

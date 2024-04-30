import React from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';

const container = document.getElementById('root'); // Get the container element
const root = createRoot(container); // Create a root

if (process.env.NODE_ENV === 'development') {
  // Backup the original console.warn
  const originalWarn = console.warn;

  // Override console.warn
  console.warn = (...args) => {
    // Check for specific messages to hide
    // if (args[0].includes("Example warning message to hide")) {
    //   return; // Do not log this specific warning
    // }

    // For all other warnings, use the original console.warn
    originalWarn.apply(console, args);
  };
}

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();

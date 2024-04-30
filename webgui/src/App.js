import React, { useState } from 'react';
import axios from 'axios';

import './App.css';

function App() {
  const [formData, setFormData] = useState({
    log_notes: '',
    source: '',
    level: 'INFO',
    status: 'new', // uneditable
    misc: '',
    success: true,
  });

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData({
      ...formData,
      [name]: type === 'checkbox' ? checked : value,
    });
  };

  const handleSubmit = async (e) => {

    const apiPort = parseInt(process.env.REACT_APP_API_PORT) || 0;
    const secretKey = process.env.REACT_APP_SECRET_KEY || null;

    e.preventDefault();
    try {
      // const response = await axios.post(`https://localhost:${apiPort}/add`, formData, {
      //   headers: {
      //     'Content-Type': 'application/json',
      //     'X-Secret-Key': secretKey,
      //   }
      // });
      // console.log('Server Response:', response.data);
      console.log('apiPort:', apiPort);
      console.log('secretKey:', secretKey);
      alert('NOT IMPLEMENTED YET!');
    } catch (error) {
      console.error('Error submitting log:', error);
      alert('Failed to submit log');
    }
  };

  const handleClear = () => {
    setFormData({
      log_notes: '',
      source: '',
      level: 'INFO', 
      status: 'new',
      misc: '',
      success: true,
    });
  };

  const [activeButton, setActiveButton] = useState('searchLog');

  return (
    <div className="form-container">
      <h1>LoggerX Entry Form</h1>
      <div className="top-menu">
        <button 
          className={`top-button new-log ${activeButton === 'newLog' ? 'active' : ''}`} 
          onClick={() => setActiveButton('newLog')}
        >
          New Log
        </button>
        <button 
          disabled={activeButton !== 'updateLog'} 
          className={`top-button ${activeButton === 'updateLog' ? 'active' : ''}`} 
          onClick={() => setActiveButton('updateLog')}
        >
          Update Log
        </button>
        <button 
          disabled={activeButton !== 'deleteLog'} 
          className={`top-button ${activeButton === 'deleteLog' ? 'active' : ''}`} 
          onClick={() => setActiveButton('deleteLog')}
        >
          Delete Log
        </button>
      </div>
      <form onSubmit={handleSubmit} className="log-form">
        <div className="form-row log-id-uuid-container">
          <label>Log ID:</label>
          <input type="text" name="log_id" className="log-id" readOnly />
          <button className="log-id-button">←</button>
          <button className="log-id-button">→</button>
          <label className="uuid-label">UUID:</label>
          <input type="text" name="uuid" className="uuid-input" readOnly />
        </div>
        <div className="form-row">
          <label>Log Notes:</label>
          <textarea name="log_notes" value={formData.log_notes} onChange={handleChange} />
        </div>
        <div className="form-row">
          <label>Source:</label>
          <input type="text" name="source" value={formData.source} onChange={handleChange} />
        </div>
        <div className="form-row level-dropdown-container">
          <label>Level:</label>
          <select name="level" className="level-select" value={formData.level} onChange={handleChange}>
            <option value="INFO">INFO</option>
            <option value="ERROR">ERROR</option>
            <option value="DEBUG">DEBUG</option>
            <option value="WARNING">WARNING</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
        </div>
        <div className="form-row">
          <label>Misc Notes:</label>
          <textarea name="misc" value={formData.misc} onChange={handleChange} />
        </div>
        <div className="form-row checkbox-container">
          <label>Success:</label>
          <input type="checkbox" className="success-checkbox" name="success" checked={formData.success} onChange={handleChange} />
        </div>
        <div className="buttons">
          <button type="submit">Submit</button>
          <button type="button" onClick={handleClear}>Clear Form</button>
        </div>
      </form>
    </div>
  );
}

export default App;
import React, { useState } from 'react';
import axios from 'axios';

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
    e.preventDefault();
    try {
      const response = await axios.post('https://localhost:9199/add', formData, {
        headers: {
          'Content-Type': 'application/json',
          'X-Secret-Key': 'YOUR_SECRET_KEY', // Make sure to replace this with your actual secret key
        }
      });
      console.log('Server Response:', response.data);
      alert('Log submitted successfully');
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

  return (
    <div className="App">
      <h1>Log Entry Form</h1>
      <form onSubmit={handleSubmit}>
        <div>
          <label>Log Notes:</label>
          <input type="text" name="log_notes" value={formData.log_notes} onChange={handleChange} />
        </div>
        <div>
          <label>Source:</label>
          <input type="text" name="source" value={formData.source} onChange={handleChange} />
        </div>
        <div>
          <label>Level:</label>
          <select name="level" value={formData.level} onChange={handleChange}>
            <option value="INFO">INFO</option>
            <option value="ERROR">ERROR</option>
            <option value="DEBUG">DEBUG</option>
          </select>
        </div>
        <div>
          <label>Misc:</label>
          <input type="text" name="misc" value={formData.misc} onChange={handleChange} />
        </div>
        <div>
          <label>Success:</label>
          <input type="checkbox" name="success" checked={formData.success} onChange={handleChange} />
        </div>
        <button type="submit">Submit</button>
        <button type="button" onClick={handleClear}>Clear</button>
      </form>
    </div>
  );
}

export default App;

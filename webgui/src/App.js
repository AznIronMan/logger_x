import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";

import "./App.css";

function App() {
  const [formData, setFormData] = useState({
    log_id: "",
    log_notes: "",
    uuid: "",
    source: "",
    level: "INFO",
    status: "new",
    misc: "",
    admin_delete: false,
  });

  // TODO: Convert console to a log and/or alerts or notification on the webgui

  const apiURL = process.env.REACT_APP_API_URL || "localhost";
  const apiPort = parseInt(process.env.REACT_APP_API_PORT) || 0;
  const secretKey = process.env.REACT_APP_SECRET_KEY || null;
  const debugMode = false;

  const checkLogIdExists = useCallback(
    async (logId) => {
      if (!logId) {
        setButtonsActive((prev) => ({
          ...prev,
          updateLog: false,
          deleteLog: false,
        }));
        return false;
      }
      try {
        const response = await axios.get(
          `https://${apiURL}:${apiPort}/checkid/${logId}`,
          {
            headers: {
              "Content-Type": "application/json",
              "X-Secret-Key": secretKey,
            },
          }
        );
        const exists = response.data.exists;
        setButtonsActive((prev) => ({
          ...prev,
          updateLog: exists,
          deleteLog: exists,
        }));
        return exists;
      } catch (error) {
        if (debugMode) console.error("Failed to check log ID:", error);
        setButtonsActive((prev) => ({
          ...prev,
          updateLog: false,
          deleteLog: false,
        }));
        return false;
      }
    },
    [apiURL, apiPort, secretKey, debugMode]
  );

  const checkSubmission = useCallback((notes, source, level, status) => {
    const errors = [];
    if (!notes || notes.trim().length === 0) errors.push("notes");
    if (!source || source.trim().length === 0) errors.push("source");
    if (!level || level.trim().length === 0) errors.push("level");
    if (!status || status.trim().length === 0) errors.push("status");
    return errors.length > 0 ? errors : true;
  }, []);

  const clearForm = useCallback(() => {
    setFormData({
      log_id: "",
      log_notes: "",
      uuid: "",
      source: "",
      level: "INFO",
      status: "new",
      misc: "",
      admin_delete: false,
    });
  }, []);

  const fetchNewLogId = useCallback(async () => {
    try {
      const response = await axios.get(
        `https://${apiURL}:${apiPort}/newlogid`,
        {
          headers: {
            "Content-Type": "application/json",
            "X-Secret-Key": secretKey,
          },
        }
      );
      setFormData((prevFormData) => ({
        ...prevFormData,
        log_id: response.data.new_log_id || "",
        log_notes: "",
        uuid: "",
        source: "",
        level: "INFO",
        status: "new",
        misc: "",
        admin_delete: false,
      }));
      setHasNext(false); // No next log ID expected after a new log entry
      checkLogIdExists(response.data.new_log_id);
    } catch (error) {
      if (debugMode) console.error("Failed to fetch new log ID:", error);
    }
  }, [apiURL, apiPort, secretKey, debugMode, checkLogIdExists]);

  const fetchFirstLogId = useCallback(async () => {
    try {
      const response = await axios.get(
        `https://${apiURL}:${apiPort}/firstlogid`,
        {
          headers: {
            "Content-Type": "application/json",
            "X-Secret-Key": secretKey,
          },
        }
      );
      return response.data.first_log_id;
    } catch (error) {
      if (debugMode) console.error("Failed to fetch first log ID:", error);
    }
  }, [apiURL, apiPort, secretKey, debugMode]);

  useEffect(() => {
    fetchNewLogId();
  }, [fetchNewLogId]);

  const fetchNextLogId = useCallback(async () => {
    try {
      const response = await axios.get(
        `https://${apiURL}:${apiPort}/nextlogid/${formData.log_id}`,
        {
          headers: {
            "Content-Type": "application/json",
            "X-Secret-Key": secretKey,
          },
        }
      );
      if (response.data.next_log_id !== null) {
        setFormData((prevFormData) => ({
          ...prevFormData,
          log_id: response.data.next_log_id,
        }));
        setHasNext(true);
      } else {
        setHasNext(false); // No next log ID available, disable the button
      }
    } catch (error) {
      if (debugMode) console.error("Failed to fetch next log ID:", error);
      alert("Failed to fetch next log ID.");
      setHasNext(false);
    }
  }, [apiURL, apiPort, secretKey, debugMode, formData.log_id]);

  const [hasNext, setHasNext] = useState(true);

  const fetchPreviousLogId = useCallback(async () => {
    try {
      const response = await axios.get(
        `https://${apiURL}:${apiPort}/previouslogid/${formData.log_id}`,
        {
          headers: {
            "Content-Type": "application/json",
            "X-Secret-Key": secretKey,
          },
        }
      );
      if (response.data.previous_log_id !== null) {
        setFormData((prevFormData) => ({
          ...prevFormData,
          log_id: response.data.previous_log_id,
        }));
        // After setting the previous log ID, check if there's a next log ID from this point
        await checkLogIdExists(response.data.previous_log_id + 1).then(
          (exists) => {
            setHasNext(exists);
          }
        );
      } else {
        setHasPrevious(false);
      }
    } catch (error) {
      if (debugMode) console.error("Failed to fetch previous log ID:", error);
      alert("Failed to fetch previous log ID.");
      setHasPrevious(false);
    }
  }, [
    apiURL,
    apiPort,
    secretKey,
    debugMode,
    formData.log_id,
    checkLogIdExists,
  ]);

  const [hasPrevious, setHasPrevious] = useState(false);

  useEffect(() => {
    fetchNewLogId();
  }, [fetchNewLogId]);

  useEffect(() => {
    if (formData.log_id) {
      checkLogIdExists(formData.log_id).then((exists) => {
        setHasNext(exists);
        setHasPrevious(formData.log_id > 1 && exists);
      });
    }
  }, [formData.log_id, checkLogIdExists]);

  useEffect(() => {
    if (formData.log_id) {
      checkLogIdExists(formData.log_id).then((exists) => {
        setHasNext(!exists);
        setHasPrevious(formData.log_id > 1);
      });
    }
  }, [formData.log_id, checkLogIdExists]);

  useEffect(() => {
    if (debugMode) {
      console.log("Checking if log ID exists:", formData.log_id);
    }
    if (formData.log_id) {
      checkLogIdExists(formData.log_id).then((exists) => {
        if (debugMode) {
          console.log("Log ID exists:", exists);
        }
        setHasNext(exists);
      });
    }
  }, [formData.log_id, checkLogIdExists, debugMode]);

  const [firstLogId, setFirstLogId] = useState("");

  useEffect(() => {
    fetchFirstLogId().then((id) => setFirstLogId(id));
  }, [fetchFirstLogId]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData({
      ...formData,
      [name]: type === "checkbox" ? checked : value,
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const submissionCheck = checkSubmission(
      formData.log_notes,
      formData.source,
      formData.level,
      formData.status
    );
    if (submissionCheck !== true) {
      alert(
        "Please complete the required fields: " + submissionCheck.join(", ")
      );
      return;
    }
    formData.log_notes = stripInvalidCharacters(formData.log_notes);
    formData.source = stripInvalidCharacters(formData.source);
    if (formData.misc) {
      formData.misc = stripInvalidCharacters(formData.misc);
    }

    if (debugMode) console.log(formData);

    try {
      const response = await axios.post(
        `https://${apiURL}:${apiPort}/add`,
        formData,
        {
          headers: {
            "Content-Type": "application/json",
            "X-Secret-Key": secretKey,
          },
        }
      );
      if (debugMode) console.log("Server Response:", response.data);
      if (response.data.status === "success") {
        alert("Log submitted successfully!");
        clearForm();
        fetchNewLogId();
      } else {
        alert("Failed to submit log: " + response.data.message);
      }
    } catch (error) {
      if (debugMode) console.error("Error submitting log:", error);
      alert("Failed to submit log: " + error.message);
    }
  };

  const handleClear = async () => {
    const confirmed = window.confirm(
      "Are you sure you want to clear the form?"
    );

    if (!confirmed) {
      return;
    } else {
      clearForm();
      fetchNewLogId();
      if (debugMode) console.log("Form cleared");
    }
  };

  const [buttonsActive, setButtonsActive] = useState({
    newLog: true,
    submitForm: true,
    clearForm: true,
    updateLog: false,
    deleteLog: false,
  });

  const stripInvalidCharacters = (input) => {
    return input.replace(/[^a-zA-Z0-9 \-.,#]/g, "");
  };

  const toggleButton = (buttonKey) => {
    setButtonsActive((prev) => ({ ...prev, [buttonKey]: !prev[buttonKey] }));
  };

  return (
    <div className="form-container">
      <h1>LoggerX Entry Form</h1>
      <div className="top-menu">
        <button
          disabled={buttonsActive.newLog ? false : true}
          className={`button-obj new-log ${buttonsActive.newLog ? "active" : "inactive"}`}
          onClick={() => {
            // toggleButton('newLog');
            fetchNewLogId();
          }}
        >
          New Log
        </button>
        <button
          disabled={buttonsActive.updateLog ? false : true}
          className={`button-obj update-log ${buttonsActive.updateLog ? "active" : "inactive"}`}
          onClick={() => {
            console.log("Update Log Pressed");
            // toggleButton('updateLog')
          }}
        >
          Update Log
        </button>
        <button
          disabled={buttonsActive.deleteLog ? false : true}
          className={`button-obj delete-log ${buttonsActive.deleteLog ? "active" : "inactive"}`}
          onClick={() => {
            console.log("Delete Log Pressed");
            // toggleButton('deleteLog')
          }}
        >
          Delete Log
        </button>
      </div>
      <form onSubmit={handleSubmit} className="log-form">
        <div className="form-row log-id-uuid-container">
          <label>Log ID:</label>
          <input
            type="text"
            name="log_id"
            className="log-id"
            value={formData.log_id}
            readOnly
          />
          <button
            name="previousLog"
            className={`button-obj previous-log ${!hasPrevious ? "inactive" : "active"}`}
            disabled={!hasPrevious}
            type="button"
            onClick={() => {
              if (debugMode) console.log("Previous Log Pressed");
              fetchPreviousLogId();
            }}
          >
            ←
          </button>
          <button
            name="nextLog"
            className={`button-obj next-log ${hasNext ? "active" : "inactive"}`}
            disabled={!hasNext}
            type="button"
            onClick={() => {
              if (debugMode) console.log("Next Log Pressed");
              fetchNextLogId();
            }}
          >
            →
          </button>
          <label className="uuid-label">UUID:</label>
          <input
            type="text"
            name="uuid"
            className="uuid-input"
            value={formData.uuid}
            readOnly
            disabled={buttonsActive.newLog ? true : false}
          />
        </div>
        <div className="form-row">
          <label>Log Notes:</label>
          <textarea
            name="log_notes"
            value={formData.log_notes}
            onChange={handleChange}
          />
        </div>
        <div className="form-row">
          <label>Source:</label>
          <input
            type="text"
            name="source"
            value={formData.source}
            onChange={handleChange}
          />
        </div>
        <div className="form-row level-dropdown-container">
          <label>Status:</label>
          <select
            name="status"
            className="status-select"
            value={formData.status}
            onChange={handleChange}
          >
            <option value="new">NEW</option>
            <option value="onhold">ON HOLD</option>
            <option value="active">IN PROGRESS</option>
            <option value="blocked">BLOCKED</option>
            <option value="complete">COMPLETE</option>
            <option value="closed">CLOSED</option>
          </select>
          <label>&nbsp;&nbsp;&nbsp;Level:</label>
          <select
            name="level"
            className="level-select"
            value={formData.level}
            onChange={handleChange}
          >
            <option value="INFO">INFO</option>
            <option value="SUCCESS">SUCCESS</option>
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
        <div className="check-row checkbox-container">
          <label hidden={!buttonsActive.deleteLog}>Admin Delete:</label>
          <input
            type="checkbox"
            className="admin-delete-checkbox"
            name="admin_delete"
            checked={formData.admin_delete}
            onChange={handleChange}
            hidden={!buttonsActive.deleteLog}
          />
          <label>&nbsp;</label>
        </div>
        <div className="form-row" />
        <div className="buttons">
          <button
            disabled={buttonsActive.submitForm ? false : true}
            className={`button-obj submit-form ${buttonsActive.submitForm ? "active" : "inactive"}`}
            type="submit"
          >
            Submit
          </button>
          <button
            disabled={buttonsActive.clearForm ? false : true}
            className={`button-obj clear-form ${buttonsActive.clearForm ? "active" : "inactive"}`}
            type="button"
            onClick={handleClear}
          >
            Clear Form
          </button>
        </div>
      </form>
    </div>
  );
}

export default App;

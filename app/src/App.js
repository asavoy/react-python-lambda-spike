import React from "react";
import { useEffect, useState } from "react";
import "./App.css";

const API_SERVER_HOST = document.location.origin;

function App() {
  const [date, setDate] = useState(null);
  useEffect(() => {
    async function getDate() {
      const res = await fetch(API_SERVER_HOST + "/api/date");
      const newDate = (await res.json())["date"];
      setDate(newDate);
    }
    getDate();
  }, []);
  return (
    <div className="App">
      <h2>
        The current date on the Python server at '{API_SERVER_HOST}' is...
      </h2>
      <p>{date ? date : "Fetching date..."}</p>
    </div>
  );
}

export default App;
const q = selector => document.querySelector(selector);

function textFor(event) {
  const data = event.data || {};
  if (data.incident) return data.incident.report;
  if (data.label) return data.label;
  if (data.message) return data.message;
  if (data.tool) return "Tool selected: " + data.tool;
  if (data.code) return "Status: " + data.code;
  return "TraceRoot recorded an investigation event.";
}

function classify(event) {
  if (event.type.includes("error") || event.type.includes("failed")) return "event-error";
  if (event.type.includes("tool")) return "event-tool";
  if (event.type.includes("message")) return "event-message";
  return "event-system";
}

export function addEvent(event) {
  if (event.type === "workspace.ready") return;
  const date = event.at ? new Date(event.at) : new Date();
  const article = document.createElement("article");
  article.className = "event " + classify(event);
  article.innerHTML = '<div class="event-marker"></div><div class="event-content"><div class="event-meta"><b></b><time></time></div><p></p></div>';
  article.querySelector("b").textContent = event.type.replaceAll(".", " ").toUpperCase();
  article.querySelector("time").textContent = date.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"});
  article.querySelector("p").textContent = textFor(event);
  q("#timeline").append(article);
  article.scrollIntoView({block:"end", behavior:"smooth"});
  if (event.type === "incident.reported") {
    q("#run-name").textContent = "Incident " + event.data.incident.id;
    q("#run-status").textContent = "REPORTED";
  }
  if (event.type === "agent.started" && event.data.label === "Evidence Auditor") q("#auditor-status").textContent = "Reviewing evidence";
  if (event.type === "agent.started" && event.data.label === "Investigator") q("#investigator-status").textContent = "Investigating";
}

export function setConnection(status) {
  q("#connection").firstChild.nodeValue = status;
}
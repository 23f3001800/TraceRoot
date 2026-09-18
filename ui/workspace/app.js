const q = selector => document.querySelector(selector);
const timeline = q("#timeline");
function eventClass(type) {
  if (type.includes("tool")) return "tool";
  if (type.includes("error") || type.includes("failed")) return "error";
  if (type.includes("message") || type.includes("pause") || type.includes("resume")) return "user";
  return "system";
}
function describe(trace) {
  const data = trace.data || {};
  if (data.incident) return data.incident.report;
  if (data.label) return data.label;
  if (data.message) return data.message;
  if (data.tool) return "Tool: " + data.tool;
  if (data.code) return "Provider or tool status: " + data.code;
  return "Investigation event recorded.";
}
function addEvent(trace) {
  const type = trace.type || "system";
  const time = trace.at ? new Date(trace.at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}) : "NOW";
  const label = type.replaceAll(".", " ").toUpperCase();
  timeline.insertAdjacentHTML("beforeend", '<article class="event '+eventClass(type)+'"><div class="event-line"><span></span></div><time>'+time+'</time><div class="event-card"><div class="event-meta"><b>'+label+'</b><span>trace</span></div><p></p></div></article>');
  timeline.lastElementChild.querySelector("p").textContent = describe(trace);
  timeline.lastElementChild.scrollIntoView({block:"end", behavior:"smooth"});
}
async function post(url, data = {}) {
  const response = await fetch(url, {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded"}, body:new URLSearchParams(data)});
  const body = await response.json();
  if (!response.ok) throw Error(body.message || "Request failed.");
  return body;
}
q("#report").onsubmit = async e => {
  e.preventDefault();
  try {
    const result = await post("/api/incidents", Object.fromEntries(new FormData(e.currentTarget)));
    q("#run-name").textContent = "Incident " + result.item.id;
    q("#run-status").textContent = "REPORTED";
    e.currentTarget.reset();
  } catch (error) { addEvent({type:"workspace.error", data:{message:error.message}}); }
};
q("#message").onsubmit = async e => {
  e.preventDefault(); const input = e.currentTarget.message;
  if (!input.value.trim()) return;
  try { await post("/api/messages", {message:input.value}); input.value=""; }
  catch (error) { addEvent({type:"workspace.error", data:{message:error.message}}); }
};
q("#pause").onclick = () => post("/api/pause").catch(error => addEvent({type:"workspace.error",data:{message:error.message}}));
q("#resume").onclick = () => post("/api/resume").catch(error => addEvent({type:"workspace.error",data:{message:error.message}}));
const sse = new EventSource("/api/events");
sse.onopen = () => { q("#connection").innerHTML = "<i></i>Live"; };
sse.addEventListener("trace", message => { const trace = JSON.parse(message.data); if (trace.type !== "workspace.ready") addEvent(trace); });
sse.onerror = () => { q("#connection").innerHTML = "<i></i>Reconnecting"; };

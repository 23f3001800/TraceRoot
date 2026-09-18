export async function post(path, data = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/x-www-form-urlencoded"},
    body: new URLSearchParams(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "Request failed.");
  return result;
}

export function connectEvents(onEvent, onStatus) {
  const stream = new EventSource("/api/events");
  stream.onopen = () => onStatus("Live");
  stream.onerror = () => onStatus("Reconnecting");
  stream.addEventListener("trace", message => onEvent(JSON.parse(message.data)));
  return stream;
}
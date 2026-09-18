import {connectEvents, post} from "./api.js";
import {addEvent, setConnection} from "./renderer.js";

const q = selector => document.querySelector(selector);
q("#focus-intake").onclick = () => q("#intake").scrollIntoView({behavior:"smooth"});
q("#report").onsubmit = async event => {
  event.preventDefault();
  try {
    await post("/api/incidents", Object.fromEntries(new FormData(event.currentTarget)));
    event.currentTarget.reset();
  } catch (error) {
    addEvent({type:"workspace.error", data:{message:error.message}});
  }
};
q("#message").onsubmit = async event => {
  event.preventDefault();
  const input = event.currentTarget.message;
  if (!input.value.trim()) return;
  try {
    await post("/api/messages", {message:input.value});
    input.value = "";
  } catch (error) {
    addEvent({type:"workspace.error", data:{message:error.message}});
  }
};
q("#pause").onclick = () => post("/api/pause").catch(error => addEvent({type:"workspace.error", data:{message:error.message}}));
q("#resume").onclick = () => post("/api/resume").catch(error => addEvent({type:"workspace.error", data:{message:error.message}}));
connectEvents(addEvent, setConnection);
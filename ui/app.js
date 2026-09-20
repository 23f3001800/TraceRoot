let digest = '';
const notice = document.getElementById('notice');
function render(data) {
  for (const key of ['investigation', 'repository', 'session', 'hash'])
    document.getElementById(key).textContent = data[key];
  document.getElementById('patch').textContent = data.patch;
  digest = data.hash;
}
fetch('/api/approval-context').then(async response => {
  if (!response.ok) throw new Error('Cannot load approval context.');
  render(await response.json());
}).catch(error => { notice.textContent = error.message; });
const stream = new EventSource('/api/events');
stream.addEventListener('trace', event => {
  const data = JSON.parse(event.data).data;
  if (data.type === 'approval_context') render(data);
  if (data.type === 'approval_created')
    notice.textContent = data.message + ' Approval ID: ' + data.approval_id;
});
document.getElementById('approval-form').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const response = await fetch('/api/approve', {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ approved_by: document.getElementById('approver').value, patch_hash: digest })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || 'Approval failed.');
    notice.textContent = data.message + ' Approval ID: ' + data.approval_id;
  } catch (error) { notice.textContent = error.message; }
});

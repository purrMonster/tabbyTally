export function nextRange(state, mailbox) {
  const validity = String(mailbox.uidValidity);
  if (state && state.uid_validity !== validity) {
    throw new Error('UIDVALIDITY changed: stop and reconcile mailbox identity before resuming');
  }
  const end = Number(mailbox.uidNext) - 1;
  const last = state ? Number(state.last_uid) : end;
  return { validity, last, end, range: last < end ? `${last + 1}:${end}` : null };
}

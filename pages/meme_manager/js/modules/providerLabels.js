export function formatProviderLabel({ id, name }) {
  const providerId = String(id ?? '').trim();
  const displayName = String(name ?? '').trim();

  if (displayName && providerId && displayName !== providerId) {
    return `${displayName} (${providerId})`;
  }
  return displayName || providerId;
}

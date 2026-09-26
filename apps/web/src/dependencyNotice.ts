import type { Health } from './api'

export function dependencyNotice(services: Health['services']) {
  const impaired = Object.entries(services).filter(([, state]) => state !== 'ok')
  if (services.mongodb === 'unconfigured') {
    const otherIssues = impaired.filter(([service]) => service !== 'mongodb').map(([service, state]) => `${service}: ${state}`)
    return `Local-only mode. MongoDB Atlas is not configured; deterministic storage is active.${otherIssues.length ? ` Other dependencies: ${otherIssues.join(' · ')}.` : ''}`
  }
  if (services.mongodb === 'degraded') {
    const otherIssues = impaired.filter(([service]) => service !== 'mongodb').map(([service, state]) => `${service}: ${state}`)
    return `Atlas connectivity is degraded; affected requests may fail until MongoDB recovers.${otherIssues.length ? ` Other dependencies: ${otherIssues.join(' · ')}.` : ''}`
  }
  return `Limited mode. ${impaired.map(([service, state]) => `${service}: ${state}`).join(' · ')}.`
}

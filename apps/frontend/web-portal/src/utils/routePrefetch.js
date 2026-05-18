const prefetchedRouteNames = new Set()
const pendingRouteNames = new Set()

function canPrefetch() {
  if (typeof window === 'undefined') {
    return false
  }

  const connection = window.navigator?.connection
  if (connection?.saveData) {
    return false
  }
  if (connection?.effectiveType && /(^|-)2g$/.test(connection.effectiveType)) {
    return false
  }

  return true
}

function resolveRouteLoader(routeRecord) {
  if (!routeRecord) {
    return null
  }

  const componentLoader = routeRecord.components?.default || routeRecord.component
  return typeof componentLoader === 'function' ? componentLoader : null
}

export async function prefetchRouteByName(router, routeName) {
  if (!canPrefetch() || !router || !routeName || prefetchedRouteNames.has(routeName) || pendingRouteNames.has(routeName)) {
    return
  }

  const routeRecord = router.getRoutes().find((item) => item.name === routeName)
  const loader = resolveRouteLoader(routeRecord)
  if (!loader) {
    prefetchedRouteNames.add(routeName)
    return
  }

  pendingRouteNames.add(routeName)
  try {
    await Promise.resolve(loader())
    prefetchedRouteNames.add(routeName)
  } catch (error) {
    console.debug(`prefetch route failed: ${String(routeName)}`, error)
  } finally {
    pendingRouteNames.delete(routeName)
  }
}

export function prefetchRoutesOnIdle(router, routeNames = []) {
  if (!canPrefetch() || !Array.isArray(routeNames) || !routeNames.length) {
    return
  }

  const uniqueRouteNames = Array.from(new Set(routeNames.filter(Boolean)))
    .filter((routeName) => routeName !== router?.currentRoute?.value?.name)
    .slice(0, 2)
  if (!uniqueRouteNames.length) {
    return
  }

  const run = () => {
    uniqueRouteNames.forEach((routeName, index) => {
      window.setTimeout(() => {
        prefetchRouteByName(router, routeName)
      }, index * 220)
    })
  }

  if (typeof window.requestIdleCallback === 'function') {
    window.requestIdleCallback(run, { timeout: 2500 })
    return
  }

  window.setTimeout(run, 900)
}

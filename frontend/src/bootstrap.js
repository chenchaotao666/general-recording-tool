// The initial route may load asynchronously or redirect before the app can
// determine its layout. Keep the startup placeholder until that work completes.
export async function mountAfterRouteReady(app, router, target = '#app') {
  await router.isReady()
  return app.mount(target)
}

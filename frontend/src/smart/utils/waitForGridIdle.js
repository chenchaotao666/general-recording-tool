// Do not apply a background snapshot while the user is moving the viewport.
// Recheck validity after waiting: a newer request or navigation supersedes it.
export async function waitForGridIdle(isBusy, isCurrent) {
  while (isCurrent() && isBusy()) {
    await new Promise(resolve => setTimeout(resolve, 120))
  }
  return isCurrent()
}

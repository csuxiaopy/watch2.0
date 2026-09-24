export async function toggleFullscreen(element: HTMLElement, doc: Document = document): Promise<void> {
  if (doc.fullscreenElement === element) {
    if (!doc.exitFullscreen) throw new Error('当前浏览器不支持退出全屏')
    await doc.exitFullscreen()
    return
  }
  if (!element.requestFullscreen) throw new Error('当前浏览器不支持视频墙全屏')
  await element.requestFullscreen()
}


/**
 * 缠论中枢矩形 — lightweight-charts v4 primitive (官方 plugin API 结构)
 *
 * 关键(照官方 rectangle-drawing-tool 示例):
 * - paneView.update() 里预计算坐标(series.priceToCoordinate + chart.timeScale().timeToCoordinate)
 * - renderer() 每次返回新 renderer 实例
 * - draw() 里用 useBitmapCoordinateSpace 画矩形
 */
class ZsPaneRenderer {
  constructor(zones, chart, series) {
    this._zones = zones;   // [{x1,y1,x2,y2}] 已算好像素坐标
    this._chart = chart;
    this._series = series;
  }
  draw(target) {
    target.useBitmapCoordinateSpace(scope => {
      const ctx = scope.context;
      const hr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
      ctx.save();
      ctx.lineWidth = Math.max(1, Math.floor(hr * 1));
      for (const z of this._zones) {
        if (z.x1 == null || z.x2 == null || z.y1 == null || z.y2 == null) continue;
        const X = Math.min(z.x1, z.x2) * hr;
        const Y = Math.min(z.y1, z.y2) * vr;
        const W = Math.abs(z.x2 - z.x1) * hr;
        const H = Math.abs(z.y2 - z.y1) * vr;
        ctx.fillStyle = 'rgba(255,215,0,0.16)';
        ctx.fillRect(X, Y, W, H);
        ctx.strokeStyle = 'rgba(255,215,0,0.9)';
        ctx.strokeRect(X, Y, W, H);
        ctx.fillStyle = 'rgba(255,215,0,0.95)';
        ctx.font = `bold ${Math.floor(13 * hr)}px sans-serif`;
        ctx.fillText('ZG ' + z.zg.toFixed(2), X + 4 * hr, Math.max(Y - 6 * vr, 12 * vr));
        ctx.fillText('ZD ' + z.zd.toFixed(2), X + 4 * hr, Y + H + 14 * vr);
      }
      ctx.restore();
    });
  }
}

class ZsPaneView {
  constructor(source) {
    this._source = source;
    this._zones = [];  // 计算后的像素坐标
  }
  update() {
    const series = this._source._series;
    const ts = this._source._chart.timeScale();
    this._zones = this._source._zones.map(z => ({
      x1: ts.timeToCoordinate(z.sdt),
      x2: ts.timeToCoordinate(z.edt),
      y1: series.priceToCoordinate(z.zg),
      y2: series.priceToCoordinate(z.zd),
      zg: z.zg, zd: z.zd,
    }));
  }
  renderer() {
    return new ZsPaneRenderer(this._zones, this._source._chart, this._source._series);
  }
}

class ZsRectanglePrimitive {
  constructor(series, zones, chart) {
    this._series = series;
    this._zones = zones || [];
    this._chart = chart;
    this._views = [new ZsPaneView(this)];
  }
  updateAllViews() {
    this._views.forEach(v => v.update());
  }
  paneViews() {
    return this._views;
  }
}
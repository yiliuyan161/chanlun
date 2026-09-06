/** 
 * 缠论中枢矩形 — lightweight-charts v4 series primitive (plugin API)
 * 官方推荐: series.attachPrimitive(ISeriesPrimitive)
 */
class ZsRectanglePrimitive {
  constructor(series, zones) {
    this._series = series;
    this._zones = zones || [];
    this._views = [new ZsPaneView(this)];
  }
  updateAllViews() {}
  paneViews() { return this._views; }
}

class ZsPaneView {
  constructor(source) { this._source = source; this._renderer = new ZsRenderer(source); }
  update() {}
  renderer() { return this._renderer; }
}

class ZsRenderer {
  constructor(source) { this._source = source; }
  draw(target) {
    target.useBitmapCoordinateSpace(scope => {
      const ctx = scope.context;
      const series = this._source._series;
      const chart = series.chart ? series.chart() : null;
      const ts = chart ? chart.timeScale() : null;
      const ps = series.priceScale();
      const hr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
      ctx.save();
      ctx.lineWidth = Math.max(1, Math.floor(hr * 1));
      for (const z of this._source._zones) {
        const x1 = ts ? ts.timeToCoordinate(z.sdt) : null;
        const x2 = ts ? ts.timeToCoordinate(z.edt) : null;
        const y1 = ps.priceToCoordinate(z.zg);
        const y2 = ps.priceToCoordinate(z.zd);
        if (x1 == null || x2 == null || y1 == null || y2 == null) continue;
        const X = Math.min(x1, x2) * hr;
        const Y = Math.min(y1, y2) * vr;
        const W = Math.abs(x2 - x1) * hr;
        const H = Math.abs(y2 - y1) * vr;
        ctx.fillStyle = 'rgba(255,215,0,0.14)';
        ctx.fillRect(X, Y, W, H);
        ctx.strokeStyle = 'rgba(255,215,0,0.85)';
        ctx.strokeRect(X, Y, W, H);
        // ZG / ZD 标签
        ctx.fillStyle = 'rgba(255,215,0,0.95)';
        ctx.font = `bold ${Math.floor(13 * hr)}px sans-serif`;
        ctx.fillText('ZG ' + z.zg.toFixed(2), X + 4 * hr, Math.max(Y - 6 * vr, 12 * vr));
        ctx.fillText('ZD ' + z.zd.toFixed(2), X + 4 * hr, Y + H + 14 * vr);
      }
      ctx.restore();
    });
  }
}
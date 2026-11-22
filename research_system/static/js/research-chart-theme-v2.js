/* research_system ECharts visual adapter v2
   Only adjusts presentation. It does not modify series data, axes values,
   statistics, API payloads, filters, or business behavior. */
(function () {
  if (!window.echarts || window.__researchChartThemeV2Installed) return;
  window.__researchChartThemeV2Installed = true;

  const PALETTE = ['#2F6BFF', '#58A6FF', '#D4A017', '#8B9BB4', '#34A853', '#F59E0B'];
  const COLOR_MAP = new Map([
    ['#409eff', '#2F6BFF'],
    ['#0a2343', '#0A2463'],
    ['#d4af37', '#D4A017'],
    ['#67c23a', '#34A853'],
    ['#e6a23c', '#F59E0B'],
    ['#909399', '#8B9BB4']
  ]);

  function remapColor(value) {
    if (typeof value !== 'string') return value;
    return COLOR_MAP.get(value.toLowerCase()) || value;
  }

  function patchColorFields(obj) {
    if (!obj || typeof obj !== 'object') return;
    for (const key of Object.keys(obj)) {
      const val = obj[key];
      if ((key === 'color' || key === 'borderColor') && typeof val === 'string') {
        obj[key] = remapColor(val);
      } else if (val && typeof val === 'object') {
        patchColorFields(val);
      }
    }
  }

  function axisStyle(axis) {
    if (!axis || typeof axis !== 'object') return;
    axis.axisLabel = Object.assign({ color: '#667085', fontSize: 12 }, axis.axisLabel || {});
    axis.axisLine = Object.assign({}, axis.axisLine || {}, {
      lineStyle: Object.assign({ color: '#E5E7EB' }, (axis.axisLine || {}).lineStyle || {})
    });
    axis.axisTick = Object.assign({ show: false }, axis.axisTick || {});
    if (axis.type !== 'category' || axis.splitLine) {
      axis.splitLine = Object.assign({}, axis.splitLine || {}, {
        lineStyle: Object.assign(
          { color: '#E5E7EB', type: 'dashed' },
          (axis.splitLine || {}).lineStyle || {}
        )
      });
    }
  }

  function normalizeOption(option) {
    if (!option || typeof option !== 'object') return option;

    option.backgroundColor = 'transparent';
    if (!option.color) option.color = PALETTE.slice();

    const legends = Array.isArray(option.legend) ? option.legend : (option.legend ? [option.legend] : []);
    legends.forEach((legend) => {
      legend.textStyle = Object.assign({ color: '#667085', fontSize: 12 }, legend.textStyle || {});
    });

    const tooltips = Array.isArray(option.tooltip) ? option.tooltip : (option.tooltip ? [option.tooltip] : []);
    tooltips.forEach((tooltip) => {
      tooltip.backgroundColor = '#FFFFFF';
      tooltip.borderColor = '#E5E7EB';
      tooltip.borderWidth = tooltip.borderWidth == null ? 1 : tooltip.borderWidth;
      tooltip.textStyle = Object.assign({ color: '#333333', fontSize: 13 }, tooltip.textStyle || {});
      tooltip.extraCssText = (tooltip.extraCssText || '') + ';box-shadow:0 4px 16px rgba(0,0,0,.10);';
    });

    const xAxes = Array.isArray(option.xAxis) ? option.xAxis : (option.xAxis ? [option.xAxis] : []);
    const yAxes = Array.isArray(option.yAxis) ? option.yAxis : (option.yAxis ? [option.yAxis] : []);
    xAxes.forEach(axisStyle);
    yAxes.forEach(axisStyle);

    const series = Array.isArray(option.series) ? option.series : [];
    series.forEach((s, index) => {
      if (!s || typeof s !== 'object') return;

      if (s.type === 'line') {
        s.lineStyle = Object.assign({ width: 3 }, s.lineStyle || {});
        s.symbol = s.symbol || 'circle';
        if (s.symbolSize == null) s.symbolSize = 8;
      }
      if (s.type === 'pie') {
        s.itemStyle = Object.assign(
          { borderColor: '#fff', borderWidth: 2, borderRadius: 0 },
          s.itemStyle || {}
        );
      }
      if (s.type === 'bar') {
        if (s.barMaxWidth == null && s.barWidth == null) s.barMaxWidth = 32;
      }

      if (!s.itemStyle) s.itemStyle = {};
      if (!s.itemStyle.color && ['line', 'bar', 'scatter'].includes(s.type)) {
        s.itemStyle.color = PALETTE[index % PALETTE.length];
      }
      if (s.type === 'line' && s.lineStyle && !s.lineStyle.color) {
        s.lineStyle.color = PALETTE[index % PALETTE.length];
      }
    });

    patchColorFields(option);
    return option;
  }

  const originalInit = window.echarts.init.bind(window.echarts);
  window.echarts.init = function () {
    const chart = originalInit.apply(window.echarts, arguments);
    if (!chart.__researchThemePatched) {
      chart.__researchThemePatched = true;
      const originalSetOption = chart.setOption.bind(chart);
      chart.setOption = function (option) {
        if (option && typeof option === 'object') normalizeOption(option);
        return originalSetOption.apply(chart, arguments);
      };
    }
    return chart;
  };
})();

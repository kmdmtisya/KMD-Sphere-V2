"use client";

/**
 * Apache ECharts, loaded with only the parts the portal uses (ADR-0018), rendered as SVG so text
 * stays crisp at any zoom.
 */
import { LineChart, PieChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { SVGRenderer } from "echarts/renderers";

echarts.use([LineChart, PieChart, GridComponent, TooltipComponent, SVGRenderer]);

export { echarts };

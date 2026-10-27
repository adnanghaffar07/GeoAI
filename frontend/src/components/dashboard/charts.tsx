import { Table2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
  type TooltipValueType,
} from 'recharts'

/** Props Recharts passes to a custom tooltip (values can be numbers or text). */
type TipProps = TooltipContentProps<TooltipValueType, string | number>

import { CHROME } from '@/lib/chart-colors'
import { cn } from '@/lib/utils'

const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

/** A card for one chart, with a "Table" switch so every value is readable without hovering. */
export function ChartCard({
  title,
  subtitle,
  table,
  children,
  className,
}: {
  title: string
  subtitle?: string
  table: { columns: string[]; rows: (string | number)[][] }
  children: ReactNode
  className?: string
}) {
  const [asTable, setAsTable] = useState(false)
  return (
    <section className={cn('panel flex min-w-0 flex-col p-4', className)} aria-label={title}>
      <header className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h3 className="font-medium">{title}</h3>
          {subtitle && <p className="text-xs text-asphalt-500">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={() => setAsTable((value) => !value)}
          aria-pressed={asTable}
          className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-asphalt-600 hover:bg-asphalt-100"
        >
          <Table2 className="size-3.5" aria-hidden />
          {asTable ? 'Chart' : 'Table'}
        </button>
      </header>
      {asTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-asphalt-500">
              <tr>
                {table.columns.map((column) => (
                  <th key={column} className="py-1 pr-3 font-medium">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, index) => (
                <tr key={index} className="border-t border-asphalt-100">
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className={cn('py-1 pr-3', typeof cell === 'number' && 'tabular-nums')}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}
    </section>
  )
}

/** Tooltip box shared by all charts: label on top, one row per value with its colour. */
function TooltipBox({ title, rows }: { title: string; rows: { name: string; value: number; color: string }[] }) {
  return (
    <div className="rounded-lg border border-asphalt-100 bg-white px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-asphalt-900">{title}</p>
      {rows.map((row) => (
        <p key={row.name} className="flex items-center gap-2 text-asphalt-700">
          <span className="size-2.5 rounded-sm" style={{ background: row.color }} aria-hidden />
          <span className="flex-1">{row.name}</span>
          <span className="font-medium tabular-nums text-asphalt-900">{row.value}</span>
        </p>
      ))}
    </div>
  )
}

export interface SeriesSpec {
  key: string
  name: string
  color: string
}

/** Several counts per day on one axis (all are counts, so one scale is honest). */
export function ActivityChart({ data, series }: { data: Record<string, number | string>[]; series: SeriesSpec[] }) {
  const tooltip = ({ active, payload, label }: TipProps) =>
    active && payload?.length ? (
      <TooltipBox
        title={shortDate(String(label))}
        rows={series.map((item) => ({ name: item.name, value: Number(payload.find((p) => p.dataKey === item.key)?.value ?? 0), color: item.color }))}
      />
    ) : null
  return (
    <div>
      <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-asphalt-700" aria-label="Legend">
        {series.map((item) => (
          <li key={item.key} className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded" style={{ background: item.color }} aria-hidden />
            {item.name}
          </li>
        ))}
      </ul>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid vertical={false} stroke={CHROME.grid} />
            <XAxis
              dataKey="date"
              tickFormatter={shortDate}
              tick={{ fontSize: 11, fill: CHROME.muted }}
              axisLine={{ stroke: CHROME.axis }}
              tickLine={false}
              minTickGap={24}
            />
            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: CHROME.muted }} axisLine={false} tickLine={false} width={44} />
            <Tooltip content={tooltip} cursor={{ stroke: CHROME.axis }} />
            {series.map((item) => (
              <Line
                key={item.key}
                type="monotone"
                dataKey={item.key}
                name={item.name}
                stroke={item.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: '#ffffff', strokeWidth: 2 }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export interface Slice {
  key: string
  name: string
  value: number
  color: string
}

/** Part of a whole at a glance (few slices), always with names and numbers beside it. */
export function DonutChart({ slices, centerLabel, onSelect }: { slices: Slice[]; centerLabel: string; onSelect?: (key: string) => void }) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0)
  const tooltip = ({ active, payload }: TipProps) => {
    const slice = active && payload?.[0] ? slices.find((item) => item.name === payload[0]!.name) : undefined
    return slice ? <TooltipBox title={slice.name} rows={[{ name: `${Math.round((slice.value / Math.max(total, 1)) * 100)}% of ${total}`, value: slice.value, color: slice.color }]} /> : null
  }
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative size-40 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices.filter((slice) => slice.value > 0)}
              dataKey="value"
              nameKey="name"
              innerRadius="62%"
              outerRadius="100%"
              stroke="#ffffff"
              strokeWidth={slices.filter((slice) => slice.value > 0).length > 1 ? 2 : 0}
              isAnimationActive={false}
              onClick={(entry: { payload?: { key?: string } }) => entry.payload?.key && onSelect?.(entry.payload.key)}
              style={{ cursor: onSelect ? 'pointer' : 'default' }}
            >
              {slices
                .filter((slice) => slice.value > 0)
                .map((slice) => (
                  <Cell key={slice.key} fill={slice.color} />
                ))}
            </Pie>
            <Tooltip content={tooltip} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold">{total}</span>
          <span className="text-xs text-asphalt-500">{centerLabel}</span>
        </div>
      </div>
      <ul className="w-full space-y-1.5 text-sm">
        {slices.map((slice) => (
          <li key={slice.key}>
            <button
              type="button"
              disabled={!onSelect}
              onClick={() => onSelect?.(slice.key)}
              className="flex w-full items-center gap-2 rounded px-1 py-0.5 text-left enabled:hover:bg-asphalt-50"
            >
              <span className="size-3 shrink-0 rounded-sm" style={{ background: slice.color }} aria-hidden />
              <span className="flex-1">{slice.name}</span>
              <span className="font-medium tabular-nums">{slice.value}</span>
              <span className="w-10 text-right text-xs text-asphalt-500 tabular-nums">{Math.round((slice.value / Math.max(total, 1)) * 100)}%</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export interface BarItem {
  key: string
  name: string
  value: number
  color: string
}

/** Horizontal bars with the value at the end; clicking a bar can open the matching list. */
export function BarList({ items, onSelect }: { items: BarItem[]; onSelect?: (key: string) => void }) {
  const tooltip = ({ active, payload }: TipProps) => {
    const item = active && payload?.[0] ? items.find((entry) => entry.name === payload[0]!.payload?.name) : undefined
    return item ? <TooltipBox title={item.name} rows={[{ name: 'Findings', value: item.value, color: item.color }]} /> : null
  }
  return (
    <div style={{ height: Math.max(items.length * 40, 60) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={items} layout="vertical" margin={{ top: 0, right: 36, bottom: 0, left: 0 }} barCategoryGap={10}>
          <XAxis type="number" hide allowDecimals={false} domain={[0, 'dataMax']} />
          <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 12, fill: CHROME.ink }} axisLine={false} tickLine={false} />
          <Tooltip content={tooltip} cursor={{ fill: '#f1f3f5' }} />
          <Bar
            dataKey="value"
            radius={[0, 4, 4, 0]}
            isAnimationActive={false}
            onClick={(entry: { payload?: { key?: string } }) => entry.payload?.key && onSelect?.(entry.payload.key)}
            style={{ cursor: onSelect ? 'pointer' : 'default' }}
          >
            {items.map((item) => (
              <Cell key={item.key} fill={item.color} />
            ))}
            <LabelList dataKey="value" position="right" style={{ fontSize: 12, fill: CHROME.ink }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** A tiny trend line for a number card (no axes; the card's number is the headline). */
export function Sparkline({ values, color }: { values: number[]; color: string }) {
  return (
    <div className="h-10" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={values.map((value, index) => ({ index, value }))} margin={{ top: 4, right: 2, bottom: 2, left: 2 }}>
          <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

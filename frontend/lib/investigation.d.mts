type LogTick = { time_minutes: number; active_replicas: number; backlog_docs: number; slo_violated: boolean };
export type LogLine = { time: number; tone: 'reactive' | 'anticipatory' | 'risk'; text: string };
export function clock(minutes: number): string;
export function investigationLog(reactive?: { ticks: LogTick[] }, anticipatory?: { ticks: LogTick[] }): LogLine[];

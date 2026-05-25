export type MonitoringRangeType = "DAILY" | "WEEKLY" | "MONTHLY" | "CUSTOM";

export type MonitoringMetricKey =
  | "SIGNUPS"
  | "ACTIVE_USERS"
  | "CHAT_MESSAGES"
  | "CHAT_SESSIONS"
  | "LIKES"
  | "DISLIKES"
  | "READING_BUTTONS";

export type MonitoringSeriesPoint = {
  date: string;
  count: number;
};

export type MonitoringMetric = {
  key: MonitoringMetricKey;
  label: string;
  description: string;
  total: number;
  series: MonitoringSeriesPoint[];
};

export type MonitoringResponse = {
  rangeType: MonitoringRangeType;
  startDate: string;
  endDate: string;
  metrics: MonitoringMetric[];
  generatedAt: string;
};
